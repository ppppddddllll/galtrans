"""本地模型翻译引擎（MarianMT 日中机翻，离线无延迟）。

设计要点：
- 模型懒加载：首次翻译时才 from_pretrained，避免拖慢程序启动。
- 线程安全：加载与推理通过同一把锁串行化。
- 路径安全：sentencepiece 无法加载含中文等非 ASCII 路径，
  模型目录自动回退到纯 ASCII 系统目录。
"""
from __future__ import annotations

import os
import threading
from typing import Any, Callable

from .base import TranslateError, TranslationEngine

# 默认模型（镜像可下载的日中机翻权重，约 300MB）
# 官方 Helsinki-NLP/opus-mt-ja-zh 未同步到 hf-mirror（401），
# 故默认用 shun89 备份（同为 opus-mt-ja-zh 权重）。
DEFAULT_MODEL = "shun89/opus-mt-ja-zh"

# 进度回调：(已完成字节, 总字节, 当前文件名)
ProgressCb = Callable[[int, int, str], None]


def _is_ascii_path(path: str) -> bool:
    """判断路径是否全为 ASCII 字符（sentencepiece 无法加载中文等非 ASCII 路径）。"""
    try:
        path.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def get_models_dir(config: Any) -> str:
    """返回模型存储目录。

    优先 config.local.models_dir；否则默认 ~/.galtrans/models，
    若含非 ASCII 字符则回退到纯 ASCII 的系统目录（ProgramData）。
    """
    local = config.get("local") or {}
    custom = (local.get("models_dir") or "").strip()
    if custom:
        return custom
    from ..config import get_config_dir

    default_dir = str(get_config_dir() / "models")
    if _is_ascii_path(default_dir):
        return default_dir
    program_data = os.environ.get("ProgramData") or r"C:\ProgramData"
    fallback = os.path.join(program_data, "galtrans", "models")
    try:
        os.makedirs(fallback, exist_ok=True)
    except OSError:
        fallback = r"C:\galtrans_models"
        os.makedirs(fallback, exist_ok=True)
    return fallback


def is_model_downloaded(config: Any, model: str | None = None) -> bool:
    """判断模型是否已下载完整（须有权重文件或完成标记，避免残留 config.json 误判）。"""
    local = config.get("local") or {}
    model = model or local.get("model") or DEFAULT_MODEL
    repo_dir = _repo_dir(get_models_dir(config), model)
    if (repo_dir / "download.ok").exists():
        return True
    # 权重文件是加载的硬性前提；仅 config.json 不算完整下载
    for name in ("pytorch_model.bin", "model.safetensors"):
        if (repo_dir / name).exists():
            return True
    return False


def _repo_dir(models_dir: str, model: str) -> Any:
    """返回模型仓库在本地目录中的存放路径。"""
    from pathlib import Path

    repo_name = model.replace("/", "__")
    return Path(models_dir) / repo_name


def _configure_endpoint(config: Any) -> None:
    """根据配置设置 HuggingFace 镜像地址（HF_ENDPOINT 环境变量）。"""
    local = config.get("local") or {}
    endpoint = (local.get("endpoint") or "").strip()
    if endpoint:
        os.environ["HF_ENDPOINT"] = endpoint


def download_model(config: Any, progress: ProgressCb | None = None) -> str:
    """下载模型到本地目录，返回模型本地路径。"""
    local = config.get("local") or {}
    model = local.get("model") or DEFAULT_MODEL
    models_dir = get_models_dir(config)
    repo_dir = _repo_dir(models_dir, model)

    if is_model_downloaded(config, model):
        return str(repo_dir)

    os.makedirs(models_dir, exist_ok=True)
    _configure_endpoint(config)

    try:
        from huggingface_hub import HfApi, hf_hub_download, list_repo_files
    except ImportError as exc:
        raise TranslateError("缺少 huggingface_hub，请先安装本地模型依赖") from exc

    skip_suffixes = (".h5", ".msgpack", ".onnx", ".ot")
    files = [f for f in list_repo_files(repo_id=model) if not f.endswith(skip_suffixes)]

    # 预估总大小（用于进度）
    file_sizes: dict[str, int] = {}
    try:
        for info in HfApi().list_repo_tree(repo_id=model):
            if getattr(info, "size", None) is not None:
                file_sizes[info.path] = info.size
    except Exception:  # noqa: BLE001
        pass
    total_bytes = sum(file_sizes.get(f, 0) for f in files)

    downloaded = 0
    try:
        for i, filename in enumerate(files):
            if progress is not None:
                progress(downloaded, total_bytes, filename)
            hf_hub_download(repo_id=model, filename=filename, local_dir=str(repo_dir))
            downloaded += file_sizes.get(filename, 0)
        if progress is not None:
            progress(downloaded, total_bytes, "完成")
        (repo_dir / "download.ok").write_text("ok", encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        raise TranslateError(f"模型下载失败：{exc}") from exc
    return str(repo_dir)


class LocalModelEngine(TranslationEngine):
    """基于本地 MarianMT 模型的离线翻译引擎。"""

    name = "local"
    needs_key = False

    def __init__(self, config: Any, glossary: Any = None) -> None:
        super().__init__(config, glossary)
        self._lock = threading.Lock()
        self._pipe: tuple[Any, Any] | None = None

    def _ensure_loaded(self) -> None:
        """懒加载模型与分词器（双检锁）。"""
        if self._pipe is not None:
            return
        with self._lock:
            if self._pipe is not None:
                return
            local = self.config.get("local") or {}
            model = local.get("model") or DEFAULT_MODEL
            models_dir = get_models_dir(self.config)
            if not is_model_downloaded(self.config, model):
                raise TranslateError(f"本地模型 {model} 未下载，请先在设置页下载模型")
            _configure_endpoint(self.config)
            try:
                from transformers import MarianMTModel, MarianTokenizer
            except ImportError as exc:
                raise TranslateError("缺少 transformers / torch，请先安装本地模型依赖") from exc
            repo_dir = _repo_dir(models_dir, model)
            try:
                self._pipe = (
                    MarianMTModel.from_pretrained(str(repo_dir)),
                    MarianTokenizer.from_pretrained(str(repo_dir)),
                )
            except Exception as exc:  # noqa: BLE001
                raise TranslateError(f"模型加载失败：{exc}") from exc

    def _translate_text(self, text: str, target_lang: str) -> str:
        """翻译单条文本。"""
        model, tokenizer = self._pipe  # type: ignore[misc]
        inputs = tokenizer([text], return_tensors="pt", truncation=True, max_length=512)
        generated = model.generate(**inputs, max_new_tokens=256)
        return tokenizer.batch_decode(generated, skip_special_tokens=True)[0]

    def translate_batch(self, texts: list[str], target_lang: str) -> list[str]:
        """批量翻译（本地模型逐条推理，保持顺序）。"""
        self._ensure_loaded()
        results: list[str] = []
        for text in texts:
            text = (text or "").strip()
            if not text:
                results.append("")
                continue
            if self.glossary is not None:
                text = self._apply_glossary(text, self.glossary)
            try:
                results.append(self._translate_text(text, target_lang))
            except TranslateError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise TranslateError(f"本地模型翻译失败：{exc}") from exc
        return results

    def health_check(self) -> bool:
        """自检：模型已下载即视为可用（不实际加载，避免 GUI 卡顿）。"""
        local = self.config.get("local") or {}
        model = local.get("model") or DEFAULT_MODEL
        return is_model_downloaded(self.config, model)
