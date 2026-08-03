"""Windows 内置 OCR 封装模块。

提供屏幕区域截屏与文字识别能力，底层使用 WinRT Windows.Media.Ocr。
- 截屏使用 Pillow ImageGrab
- 识别使用系统 OcrEngine，语言优先日文，缺失时回退用户配置语言
"""

from __future__ import annotations

import io
from typing import Optional

from PIL import Image, ImageGrab
from winrt.windows.globalization import Language
from winrt.windows.graphics.imaging import BitmapDecoder, SoftwareBitmap
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.storage.streams import (
    DataWriter,
    InMemoryRandomAccessStream,
)

# 语言引擎缓存：语言标签 -> OcrEngine 或 None
_ENGINE_CACHE: dict = {}

# 候选语言顺序：优先日文，其次中文，最后用户配置文件语言
_PREFERRED_LANGS = ("ja", "zh-Hans-CN", "zh-Hans")


class OcrError(Exception):
    """OCR 识别失败异常。"""

    pass


def get_ocr_engine(lang: str = "ja") -> Optional[OcrEngine]:
    """获取指定语言的 OCR 引擎（带缓存）。

    若指定语言不可用，依次回退到候选中文语言；仍不可用则尝试
    用户配置文件语言创建引擎；全部失败返回 None。
    """
    if lang in _ENGINE_CACHE:
        return _ENGINE_CACHE[lang]

    # 尝试目标语言 + 候选语言
    candidates = [lang, *_PREFERRED_LANGS]
    for cand in candidates:
        engine = OcrEngine.try_create_from_language(Language(cand))
        if engine is not None:
            _ENGINE_CACHE[lang] = engine
            return engine

    # 回退到用户配置文件语言
    engine = OcrEngine.try_create_from_user_profile_languages()
    _ENGINE_CACHE[lang] = engine
    return engine


def is_lang_available(lang: str) -> bool:
    """判断指定语言的 OCR 引擎是否可用（不触发回退）。

    用于界面引导用户安装对应语言包。
    """
    return OcrEngine.is_language_supported(Language(lang))


def list_available_langs() -> list[str]:
    """列出系统当前可用的 OCR 语言标签列表。

    用于界面展示「已识别语言」状态。
    """
    langs: list[str] = []
    try:
        for lang in OcrEngine.available_recognizer_languages:
            langs.append(lang.language_tag)
    except Exception:  # noqa: BLE001
        pass
    return sorted(langs)


def detect_ocr_status() -> dict:
    """检测 OCR 引擎状态，返回给界面展示。

    返回结构：
        {
            "ja_available": bool,      # 日语 OCR 是否可用
            "current_lang": str,       # 实际将使用的语言（如 'ja' 或回退语言）
            "available_langs": [...],  # 系统已安装的 OCR 语言列表
        }
    """
    available = list_available_langs()
    current = "ja" if is_lang_available("ja") else (available[0] if available else "none")
    return {
        "ja_available": is_lang_available("ja"),
        "current_lang": current,
        "available_langs": available,
    }


def capture_region(bbox: Optional[tuple] = None) -> Image.Image:
    """截取屏幕指定区域。

    参数:
        bbox: (left, top, right, bottom) 屏幕坐标矩形；None 表示全屏。
    返回:
        PIL Image 对象。
    """
    try:
        return ImageGrab.grab(bbox=bbox, all_screens=True)
    except Exception as exc:  # noqa: BLE001
        raise OcrError(f"屏幕截取失败: {exc}") from exc


def _image_to_software_bitmap(image: Image.Image) -> SoftwareBitmap:
    """将 PIL Image 转为 WinRT SoftwareBitmap。

    通过 PNG 内存流中转，使用 BitmapDecoder 解码，保证格式兼容。
    """
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    data = buffer.getvalue()

    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(data)
    writer.store_async().get()
    stream.seek(0)

    decoder = BitmapDecoder.create_async(stream).get()
    bitmap = decoder.get_software_bitmap_async().get()
    return bitmap


def ocr_image(image: Image.Image, lang: str = "ja") -> str:
    """识别图片中的文字。

    参数:
        image: PIL Image。
        lang: 期望语言标签，如 'ja'。
    返回:
        识别出的文本，按行合并（多行以换行分隔）。
    抛出:
        OcrError: 引擎不可用或识别失败。
    """
    engine = get_ocr_engine(lang)
    if engine is None:
        raise OcrError("系统未安装可用的 OCR 语言引擎")

    bitmap = _image_to_software_bitmap(image)
    result = engine.recognize_async(bitmap).get()
    lines = [line.text for line in result.lines]
    return "\n".join(lines)


def ocr_region(bbox: Optional[tuple] = None, lang: str = "ja") -> str:
    """截取屏幕区域并识别文字，一步到位。

    参数:
        bbox: 屏幕坐标矩形，None 表示全屏。
        lang: OCR 语言标签。
    返回:
        识别文本。
    """
    image = capture_region(bbox)
    return ocr_image(image, lang)
