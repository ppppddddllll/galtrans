"""配置模块：默认配置、读写与 DPAPI 密钥存取。"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

# 默认配置（新增键需在此登记；所有实例共享同一份，务必深拷贝使用）
DEFAULT_CONFIG: dict[str, Any] = {
    # 翻译调度
    "translate": {
        "primary": "deepseek",              # 首选引擎
        "fallbacks": ["deepl", "google", "bing"],  # 降级顺序
        "timeout": 30,                      # 单次请求超时（秒）
        "max_retry": 2,                     # 失败重试次数
        "concurrency": 4,                   # 并发请求数
        "rate_limit_per_min": 60,           # 每分钟请求上限
        "batch_size": 16,                   # 每批条数
        "target_lang": "zh-CN",             # 目标语言
    },
    # DeepSeek 引擎
    "deepseek": {
        "api_key": "",                      # 仅旧明文兼容，新值走 secrets_store
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "temperature": 0.8,
        "max_tokens": 4000,
    },
    # DeepL 引擎
    "deepl": {
        "api_key": "",                      # 仅旧明文兼容，新值走 secrets_store
        "api_url": "https://api-free.deepl.com/v2/translate",
    },
    # Google 免费接口
    "google": {"enabled": True},
    # Bing 免费接口
    "bing": {"enabled": True},
    # 本地模型（离线翻译）
    "local": {
        "model": "shun89/opus-mt-ja-zh",    # 镜像可下载的日中机翻模型
        "models_dir": "",                   # 空则默认（含中文路径自动回退 ASCII 目录）
        "endpoint": "",                     # HF 镜像地址（如 https://hf-mirror.com）
        "status": "",                       # 下载/加载状态提示
    },
    # OCR 配置
    "ocr": {
        "interval": 0.4,                    # 轮询间隔（秒）
        "region": None,                     # 上次框选区域 [l,t,r,b]
        "window_title": "",
    },
    # 悬浮窗（网易云歌词风格）
    "overlay": {
        "opacity": 0.92,                    # 背景不透明度 0-1
        "font_size": 16,                    # 译文字号
        "font_family": "Microsoft YaHei",
        "text_color": "#ffffff",            # 文字颜色
        "scale": 1.0,                       # 窗口缩放比例
        "position": "top",                  # top / bottom
        "history_lines": 3,                 # 保留历史行数
    },
    # 术语表
    "glossary": {"enabled": True},
}


def get_config_dir() -> Path:
    """返回配置目录，优先环境变量 GALTRANS_HOME。"""
    env = os.environ.get("GALTRANS_HOME")
    if env:
        path = Path(env)
    else:
        path = Path.home() / ".galtrans"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并两个字典，override 优先；返回全新对象，绝不污染 base。"""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


class Config:
    """配置对象，支持读写与持久化（JSON）。"""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (get_config_dir() / "config.json")
        self._data = _deep_merge(DEFAULT_CONFIG, self._load())

    def _load(self) -> dict:
        """从磁盘加载配置，失败返回空字典。"""
        if not self._path.exists():
            return {}
        try:
            with open(self._path, encoding="utf-8") as fp:
                return json.load(fp)
        except (json.JSONDecodeError, OSError):
            return {}

    def save(self) -> None:
        """持久化到磁盘。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as fp:
            json.dump(self._data, fp, ensure_ascii=False, indent=2)

    def get(self, section: str, key: str | None = None, default: Any = None) -> Any:
        """读取配置；key 为 None 时返回整个段。"""
        seg = self._data.get(section, {})
        if key is None:
            return seg
        return seg.get(key, default)

    def set(self, section: str, key: str, value: Any) -> None:
        """写入单个键并保存。"""
        self._data.setdefault(section, {})[key] = value
        self.save()

    def set_many(self, section: str, values: dict) -> None:
        """批量写入一个段并保存。"""
        self._data.setdefault(section, {}).update(values)
        self.save()

    @property
    def data(self) -> dict:
        """全部配置（调用方勿直接修改）。"""
        return self._data

    # ---------- 密钥安全存取（Windows DPAPI） ----------

    def get_secret(self, section: str) -> str:
        """读取 API Key：优先安全存储，无则迁移旧明文并清空。"""
        from .secrets_store import SecretsStore

        store = SecretsStore()
        value = store.get_key(section)
        if value:
            return value
        legacy = self.get(section, "api_key", "")
        if legacy:
            store.set_key(section, legacy)
            self.set(section, "api_key", "")
            return legacy
        return ""

    def set_secret(self, section: str, value: str) -> None:
        """写入 API Key 到安全存储，并清空配置明文。"""
        from .secrets_store import SecretsStore

        SecretsStore().set_key(section, value)
        self.set(section, "api_key", "")

    def has_secret(self, section: str) -> bool:
        """判断该段是否配置了密钥。"""
        return bool(self.get_secret(section))
