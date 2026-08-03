"""Windows 内置 OCR 封装（WinRT）。

支持截屏识别与语言检测；日语语言包缺失时自动回退到可用语言。
"""
from __future__ import annotations

import io
from typing import Any

from PIL import Image, ImageGrab


class OcrError(Exception):
    """OCR 过程中的错误。"""


_ENGINE_CACHE: dict[str, Any] = {}

# 语言优先级：日语优先，回退中文
_PREFERRED_LANGS = ("ja", "zh-Hans-CN", "zh-Hans")


def _winrt_import() -> Any:
    """惰性导入 winrt 相关模块（避免无依赖环境导入失败）。"""
    from winrt.windows.globalization import Language
    from winrt.windows.graphics.imaging import BitmapDecoder, SoftwareBitmap
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

    return (Language, BitmapDecoder, SoftwareBitmap, OcrEngine, DataWriter, InMemoryRandomAccessStream)


def is_lang_available(lang: str) -> bool:
    """判断系统是否支持指定 OCR 语言。"""
    try:
        _, _, _, OcrEngine, _, _ = _winrt_import()
        from winrt.windows.globalization import Language

        return OcrEngine.is_language_supported(Language(lang))
    except Exception:  # noqa: BLE001
        return False


def list_available_langs() -> list[str]:
    """列出系统可用的 OCR 语言标签。"""
    try:
        _, _, _, OcrEngine, _, _ = _winrt_import()
        langs = [lang.language_tag for lang in OcrEngine.available_recognizer_languages]
        return sorted(langs)
    except Exception:  # noqa: BLE001
        return []


def detect_ocr_status() -> dict[str, Any]:
    """检测 OCR 语言状态。"""
    available = list_available_langs()
    ja_available = "ja" in available
    current = "ja" if ja_available else (available[0] if available else "none")
    return {
        "ja_available": ja_available,
        "current_lang": current,
        "available_langs": available,
    }


def get_ocr_engine(lang: str = "ja") -> Any:
    """获取 OCR 引擎（带缓存与回退）。"""
    if lang in _ENGINE_CACHE:
        return _ENGINE_CACHE[lang]
    try:
        Language, _, _, OcrEngine, _, _ = _winrt_import()
    except Exception as exc:  # noqa: BLE001
        raise OcrError("Windows OCR 组件不可用") from exc

    candidates = [lang, *_PREFERRED_LANGS]
    for cand in candidates:
        try:
            engine = OcrEngine.try_create_from_language(Language(cand))
            if engine is not None:
                _ENGINE_CACHE[lang] = engine
                return engine
        except Exception:  # noqa: BLE001
            continue
    try:
        engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is not None:
            _ENGINE_CACHE[lang] = engine
            return engine
    except Exception:  # noqa: BLE001
        pass
    raise OcrError("未找到可用的 OCR 语言引擎")


def capture_region(bbox: tuple[int, int, int, int] | None = None) -> Image.Image:
    """截取屏幕区域（bbox=None 全屏，all_screens 覆盖多显示器）。"""
    try:
        return ImageGrab.grab(bbox=bbox, all_screens=True)
    except Exception as exc:  # noqa: BLE001
        raise OcrError(f"屏幕截图失败：{exc}") from exc


def _image_to_software_bitmap(image: Image.Image) -> Any:
    """把 PIL Image 转为 WinRT SoftwareBitmap（经 PNG 内存流）。"""
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(buffer.getvalue())
    writer.store_async().get()
    stream.seek(0)
    decoder = BitmapDecoder.create_async(stream).get()
    return decoder.get_software_bitmap_async().get()


def ocr_image(image: Image.Image, lang: str = "ja") -> str:
    """识别单张图片，返回按行合并的文本。"""
    engine = get_ocr_engine(lang)
    if engine is None:
        raise OcrError("未找到可用的 OCR 引擎")
    bitmap = _image_to_software_bitmap(image)
    result = engine.recognize_async(bitmap).get()
    return "\n".join(line.text for line in result.lines)


def ocr_region(bbox: tuple[int, int, int, int] | None = None, lang: str = "ja") -> str:
    """一步截屏并识别。"""
    image = capture_region(bbox)
    return ocr_image(image, lang)
