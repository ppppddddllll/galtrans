"""全局配置读写模块

使用 JSON 存储配置，默认位置：~/.galtrans/config.json
支持环境变量覆盖（便于测试与打包）。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# 默认配置结构
DEFAULT_CONFIG: dict = {
    # 翻译引擎相关
    "translate": {
        "primary": "deepseek",        # 首选引擎
        "fallbacks": ["deepl", "google", "bing"],  # 降级顺序
        "timeout": 30,                 # 单次请求超时(秒)
        "max_retry": 2,                # 单引擎重试次数
        "concurrency": 4,              # 并发请求数
        "rate_limit_per_min": 60,      # 每分钟请求上限
        "batch_size": 16,              # 批量翻译条数
        "target_lang": "zh-CN",        # 目标语言
    },
    # DeepSeek 配置
    "deepseek": {
        "api_key": "",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "temperature": 0.8,
        "max_tokens": 4000,
    },
    # DeepL 配置
    "deepl": {
        "api_key": "",
        "api_url": "https://api-free.deepl.com/v2/translate",
    },
    # Google 免费接口
    "google": {
        "enabled": True,
    },
    # Bing 免费接口
    "bing": {
        "enabled": True,
    },
    # OCR 配置
    "ocr": {
        "interval": 0.8,        # 实时翻译扫描间隔(秒)
        "region": None,         # 截图区域 [x, y, w, h]，None 表示手动框选
        "window_title": "",     # 目标窗口标题(为空则全屏)
    },
    # 悬浮窗配置
    "overlay": {
        "opacity": 0.92,
        "font_size": 16,
        "font_family": "Microsoft YaHei",
        "text_color": "#ffffff",
        "scale": 1.0,           # 窗口大小缩放比例(0.5~1.5)
        "position": "top",      # top/bottom
        "history_lines": 3,     # 保留历史行数
    },
    # 术语表
    "glossary": {
        "enabled": True,
    },
}


def get_config_dir() -> Path:
    """返回配置目录，优先环境变量 GALTRANS_HOME"""
    env = os.environ.get("GALTRANS_HOME")
    if env:
        path = Path(env)
    else:
        path = Path.home() / ".galtrans"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并两个字典，override 优先"""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class Config:
    """配置对象，支持读写与持久化"""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (get_config_dir() / "config.json")
        self._data = _deep_merge(DEFAULT_CONFIG, self._load())

    def _load(self) -> dict:
        """从磁盘加载配置"""
        if not self._path.exists():
            return {}
        try:
            with open(self._path, encoding="utf-8") as fp:
                return json.load(fp)
        except (json.JSONDecodeError, OSError):
            return {}

    def save(self) -> None:
        """持久化到磁盘"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as fp:
            json.dump(self._data, fp, ensure_ascii=False, indent=2)

    def get(self, section: str, key: str | None = None, default=None):
        """读取配置，支持分段获取"""
        if key is None:
            return self._data.get(section, {})
        return self._data.get(section, {}).get(key, default)

    def set(self, section: str, key: str, value) -> None:
        """写入配置并自动保存"""
        if section not in self._data:
            self._data[section] = {}
        self._data[section][key] = value
        self.save()

    def set_many(self, section: str, values: dict) -> None:
        """批量写入配置并保存"""
        if section not in self._data:
            self._data[section] = {}
        self._data[section].update(values)
        self.save()

    @property
    def data(self) -> dict:
        """只读访问完整配置"""
        return self._data

    # ---------- 安全密钥存取 ----------

    def get_secret(self, section: str) -> str:
        """读取某引擎的 API Key（解密）。

        优先从加密 secrets 存储读取；若不存在则回退读取 config.json
        中的旧明文，并自动迁移到加密存储（迁移成功后清空明文）。
        """
        from .secrets_store import SecretsStore

        store = SecretsStore()
        value = store.get_key(section)
        if value:
            return value

        # 兼容旧版本：读取明文并迁移
        legacy = self._data.get(section, {}).get("api_key", "")
        if legacy:
            store.set_key(section, legacy)
            self.set(section, "api_key", "")  # 清空明文
            return legacy
        return ""

    def set_secret(self, section: str, value: str) -> None:
        """加密保存某引擎的 API Key。

        密钥只写入加密存储，config.json 中保持为空串。
        """
        from .secrets_store import SecretsStore

        store = SecretsStore()
        store.set_key(section, value)
        self.set(section, "api_key", "")  # config.json 不再存明文

    def has_secret(self, section: str) -> bool:
        """判断某引擎是否已配置 API Key"""
        return bool(self.get_secret(section))
