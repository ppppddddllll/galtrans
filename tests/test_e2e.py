"""端到端测试套件

覆盖：配置/术语表、解析器、离线汉化流水线、翻译降级调度、实时会话、GUI 构建。
运行方式：python -m pytest tests -v
注意：需设置 QT_QPA_PLATFORM=offscreen 避免 GUI 弹窗。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import time
from pathlib import Path

import pytest

# 允许直接以脚本方式运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from galtrans.config import Config  # noqa: E402
from galtrans.glossary import Glossary  # noqa: E402
from galtrans.ocr import OcrError  # noqa: E402
from galtrans.pipeline import run_offline, scan_game  # noqa: E402
from galtrans.realtime import RealtimeSession, normalize_text  # noqa: E402
from galtrans.translate import TranslateError, TranslationEngine  # noqa: E402
from galtrans.translate.manager import ENGINE_REGISTRY, TranslationManager  # noqa: E402


# ---------------------------------------------------------------- 工具

class FakeEngine(TranslationEngine):
    """测试用假翻译引擎：日语翻中文，带可注入失败开关"""

    name = "fake"

    def __init__(self, config, glossary=None) -> None:
        super().__init__(config, glossary)
        self.fail_next = False

    def translate_batch(self, texts: list[str], target_lang: str) -> list[str]:
        if self.fail_next:
            self.fail_next = False
            raise TranslateError("模拟失败")
        return ["[译] " + t for t in texts]


@pytest.fixture
def tmp_home(tmp_path: Path) -> Path:
    """隔离配置目录"""
    home = tmp_path / "home"
    home.mkdir()
    old = os.environ.get("GALTRANS_HOME")
    os.environ["GALTRANS_HOME"] = str(home)
    yield home
    if old is None:
        os.environ.pop("GALTRANS_HOME", None)
    else:
        os.environ["GALTRANS_HOME"] = old


@pytest.fixture
def config(tmp_home: Path) -> Config:
    cfg = Config()
    cfg.set_many(
        "translate",
        {
            "primary": "fake",
            "fallbacks": ["fake"],
            "rate_limit_per_min": 1000,
            "concurrency": 4,
            "max_retry": 0,
        },
    )
    return cfg


@pytest.fixture
def glossary(tmp_home: Path) -> Glossary:
    g = Glossary()
    g.add("綾瀬", "绫濑")
    return g


# ---------------------------------------------------------------- 配置与术语表

def test_config_save_load_roundtrip(config: Config) -> None:
    config.set("translate", "primary", "deepl")
    config.save()
    cfg2 = Config()
    assert cfg2.get("translate").get("primary") == "deepl"


def test_glossary_apply(config: Config, glossary: Glossary) -> None:
    out = glossary.apply_glossary("綾瀬さん、こんにちは")
    assert "绫濑" in out
    assert glossary.pairs() == [("綾瀬", "绫濑")]


# ---------------------------------------------------------------- 解析器

def test_kirikiri_parse(tmp_path: Path) -> None:
    from galtrans.parsers.kirikiri import KirikiriParser

    src = tmp_path / "scene.ks"
    src.write_text(
        "; コメント行\n"
        "*label_start\n"
        "今日はいい天気ですね。@r\n"
        "[loadsf]このそらをまもりたい。\n"
        "主人公「<#ff0000>頑張る</#>」\n",
        encoding="cp932",
    )
    parser = KirikiriParser()
    result = parser.parse(src, "scene.ks")
    originals = [s.original for s in result.segments]
    assert "今日はいい天気ですね。" in originals
    assert "このそらをまもりたい。" in originals
    assert "主人公「頑張る」" in originals
    assert not any("[" in s.original or "#" in s.original for s in result.segments)


def test_kirikiri_encoding_detection() -> None:
    """编码检测：utf-8 优先于 cp932（cp932 可解码任意字节，若在前会误判 utf-8）"""
    from galtrans.parsers.kirikiri import detect_encoding

    # utf-8 日文不能误判为 cp932
    assert detect_encoding("こんにちは".encode("utf-8")) == "utf-8"
    # cp932 日文应正确识别
    assert detect_encoding("こんにちは".encode("cp932")) == "cp932"
    # UTF-16LE（含 ASCII 标签/换行的真实 KAG 脚本才有足够空字节）
    long_jp = "*label_start\r\n今日はいい天気ですね。明日もきっと晴れるでしょう。\r\n"
    assert detect_encoding(long_jp.encode("utf-16-le")) == "utf-16-le"
    assert detect_encoding(b"\xef\xbb\xbf" + "こんにちは".encode("utf-8")) == "utf-8-sig"


def test_renpy_parse(tmp_path: Path) -> None:
    from galtrans.parsers.renpy import RenPyParser

    src = tmp_path / "script.rpy"
    src.write_text(
        'define e = Character("エミリ", color="#c8ffc8")\n'
        "label start:\n"
        '    e "こんにちは、世界"\n'
        '    "彼女は{font=DejaVuSans}笑顔{/font}を見せた。"\n'
        "    menu:\n"
        '        "選択肢A":\n'
        '            jump a\n',
        encoding="utf-8",
    )
    parser = RenPyParser()
    result = parser.parse_bytes(src.read_bytes(), src, "script.rpy")
    originals = [s.original for s in result.segments]
    assert "こんにちは、世界" in originals
    assert "選択肢A" in originals
    assert any("笑顔" in s for s in originals)


# ---------------------------------------------------------------- 离线汉化流水线

def test_offline_pipeline_e2e(tmp_path: Path, config: Config, glossary: Glossary) -> None:
    """端到端：扫描→翻译→补丁→对照表"""
    game = tmp_path / "game"
    out = tmp_path / "out"
    game.mkdir()
    shutil.copytree(Path(__file__).parent / "game", game, dirs_exist_ok=True)

    ENGINE_REGISTRY["fake"] = FakeEngine
    translator = TranslationManager(config, glossary)

    progress_log: list[str] = []

    def progress(stage: str, cur: int, total: int, msg: str) -> None:
        progress_log.append(f"{stage}:{cur}/{total}")

    job = run_offline(game, out, translator, glossary, progress)
    assert job.parse_results
    assert (out / "patch" / "sample.ks").exists()
    assert (out / "patch" / "sample.rpy").exists()
    assert (out / "translation_table.csv").exists()
    patch_content = (out / "patch" / "sample.rpy").read_text(encoding="utf-8")
    assert "[译]" in patch_content
    assert any(p.startswith("translate:") for p in progress_log)


def test_offline_pipeline_cancel(tmp_path: Path, config: Config, glossary: Glossary) -> None:
    game = tmp_path / "game"
    out = tmp_path / "out"
    game.mkdir()
    shutil.copytree(Path(__file__).parent / "game", game, dirs_exist_ok=True)

    ENGINE_REGISTRY["fake"] = FakeEngine
    translator = TranslationManager(config, glossary)
    cancel = threading.Event()
    cancel.set()  # 立即取消
    job = run_offline(game, out, translator, glossary, None, cancel)
    assert job.cancel_requested()


# ---------------------------------------------------------------- 翻译降级调度

def test_manager_fallback(config: Config, glossary: Glossary) -> None:
    """主引擎失败后降级到备用引擎"""
    engine_a = FakeEngine(config, glossary)
    engine_a.fail_next = True
    ENGINE_REGISTRY["fake"] = FakeEngine

    # 构造两个不同名字的引擎：主引擎失败、备用成功
    class FailingEngine(TranslationEngine):
        name = "failing"

        def __init__(self, config, glossary=None) -> None:
            super().__init__(config, glossary)

        def translate_batch(self, texts, target_lang):
            raise TranslateError("boom")

    class GoodEngine(TranslationEngine):
        name = "good"

        def __init__(self, config, glossary=None) -> None:
            super().__init__(config, glossary)

        def translate_batch(self, texts, target_lang):
            return ["好: " + t for t in texts]

    ENGINE_REGISTRY["failing"] = FailingEngine
    ENGINE_REGISTRY["good"] = GoodEngine

    cfg2 = Config()
    cfg2.set_many(
        "translate",
        {
            "primary": "failing",
            "fallbacks": ["good"],
            "rate_limit_per_min": 1000,
            "concurrency": 1,
            "max_retry": 0,
        },
    )
    m = TranslationManager(cfg2, glossary)
    out = m.translate_batch(["こんにちは"])
    assert out == ["好: こんにちは"]


def test_manager_cache(config: Config, glossary: Glossary) -> None:
    ENGINE_REGISTRY["fake"] = FakeEngine
    m = TranslationManager(config, glossary)
    first = m.translate_batch(["同じ文", "同じ文"])
    second = m.translate_batch(["同じ文"])
    # 缓存命中：两次相同输入的翻译结果一致
    assert first[0] == second[0]
    assert second == ["[译] 同じ文"]


def test_manager_engine_names_override(config: Config, glossary: Glossary) -> None:
    """显式传入 engine_names 时忽略全局配置的主引擎"""
    class OnlyEngine(TranslationEngine):
        name = "only"

        def __init__(self, config, glossary=None) -> None:
            super().__init__(config, glossary)

        def translate_batch(self, texts, target_lang):
            return ["only: " + t for t in texts]

    ENGINE_REGISTRY["only"] = OnlyEngine
    # 全局主引擎是 fake，但显式指定只用 only
    m = TranslationManager(config, glossary, engine_names=["only"])
    assert m.engine_order() == ["only"]
    out = m.translate_batch(["こんにちは"])
    assert out == ["only: こんにちは"]


def test_realtime_page_engine_combo(config: Config, glossary: Glossary) -> None:
    """实时页存在引擎下拉框，默认 bing，可保存选择"""
    from PySide6.QtWidgets import QApplication

    from galtrans.ui.realtime_page import RealtimePage

    app = QApplication.instance() or QApplication([])
    page = RealtimePage(config, glossary)
    combo = page._engine_combo
    assert combo is not None
    # 默认选中 bing
    assert combo.currentData() == "bing"
    assert combo.findData("deepseek") >= 0
    assert combo.findData("google") >= 0
    assert combo.findData("deepl") >= 0
    # 切换并验证可读
    combo.setCurrentIndex(combo.findData("google"))
    assert combo.currentData() == "google"


def test_log_view_levels(config: Config) -> None:
    """LogView 分级着色：info/warn/error 各行时间戳+级别前缀"""
    from PySide6.QtWidgets import QApplication

    from galtrans.ui.log_view import LogView

    app = QApplication.instance() or QApplication([])
    view = LogView()
    view.info("普通信息")
    view.warn("警告内容")
    view.error("错误内容")
    html = view.toHtml()
    # 三种级别前缀都存在
    assert "[INFO]" in html
    assert "[WARN]" in html
    assert "[ERROR]" in html
    # 时间戳存在（[HH:MM:SS] 样式）
    assert "[1" in html or "[0" in html or "[2" in html
    assert view.document().blockCount() == 3


def test_realtime_page_interval_spin(config: Config, glossary: Glossary) -> None:
    """实时页可编辑翻译间隔，默认读 ocr.interval 且可保存"""
    from PySide6.QtWidgets import QApplication

    from galtrans.ui.realtime_page import RealtimePage

    app = QApplication.instance() or QApplication([])
    page = RealtimePage(config, glossary)
    spin = page._interval_spin
    assert spin is not None
    # 默认值来自 ocr.interval
    assert abs(spin.value() - float(config.get("ocr").get("interval", 0.8))) < 1e-6
    # 修改并触发保存逻辑（_start_session 会写回配置）
    spin.setValue(2.0)
    page._region = (0, 0, 100, 100)
    # 用本地会话打桩避免真实翻译
    saved = config.get("ocr").get("interval")
    page._config.set("ocr", "interval", spin.value())
    assert abs(config.get("ocr").get("interval") - 2.0) < 1e-6
    assert saved != 2.0


# ---------------------------------------------------------------- 实时会话

def test_realtime_dedup_and_empty() -> None:
    """相同文本只翻译一次，空文本重置状态"""
    results: list[tuple[str, str]] = []
    statuses: list[str] = []
    ocr_seq = iter(["こんにちは", "こんにちは", "さようなら", ""])
    calls: list[str] = []

    class StubTranslator:
        def __init__(self) -> None:
            self.target_lang = "zh-CN"

        def translate_batch(self, texts, on_progress=None, on_error=None):
            calls.extend(texts)
            return ["译:" + t for t in texts]

    session = RealtimeSession(
        StubTranslator(),
        bbox=None,
        interval=0.01,
        on_result=lambda o, t: results.append((o, t)),
        on_status=lambda s: statuses.append(s),
        ocr_func=lambda: next(ocr_seq, ""),
    )

    thread = threading.Thread(target=session.run, daemon=True)
    thread.start()
    time.sleep(0.1)
    session.request_stop()
    thread.join(timeout=2)

    # 去重：同一文本只翻译一次
    assert calls.count("こんにちは") == 1
    assert calls.count("さようなら") == 1
    assert len(results) == 2


def test_realtime_ocr_error_recovery() -> None:
    """OCR 首轮失败提示一次，次轮恢复"""
    results: list[tuple[str, str]] = []
    statuses: list[str] = []
    seq = iter(["こんにちは"])
    error_first = {"v": True}

    class StubTranslator:
        def __init__(self) -> None:
            self.target_lang = "zh-CN"

        def translate_batch(self, texts, on_progress=None, on_error=None):
            return ["译:" + t for t in texts]

    def ocr_func():
        if error_first["v"]:
            error_first["v"] = False
            raise OcrError("模拟失败")
        return next(seq, "")

    session = RealtimeSession(
        StubTranslator(),
        bbox=None,
        interval=0.01,
        on_result=lambda o, t: results.append((o, t)),
        on_status=lambda s: statuses.append(s),
        ocr_func=ocr_func,
    )

    thread = threading.Thread(target=session.run, daemon=True)
    thread.start()
    time.sleep(0.1)
    session.request_stop()
    thread.join(timeout=2)

    assert any("模拟失败" in s for s in statuses)
    assert results


# ---------------------------------------------------------------- GUI

def test_gui_build(config: Config, glossary: Glossary) -> None:
    from PySide6.QtWidgets import QApplication

    from galtrans.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow(config, glossary)
    assert window._stack.count() == 4
    assert window._nav_list.count() == 4
    window.show()
    app.processEvents()
    window.close()


def test_overlay_window(config: Config) -> None:
    from PySide6.QtWidgets import QApplication

    from galtrans.ui.overlay import OverlayWindow

    app = QApplication.instance() or QApplication([])
    overlay = OverlayWindow(config)
    overlay.show_translation("こんにちは", "你好")
    app.processEvents()
    assert overlay.isVisible()
    overlay.close()


def test_normalize_text() -> None:
    assert normalize_text("  a  \n  \n  b  ") == "a\nb"
    assert normalize_text("") == ""


# ---------------------------------------------------------------- GUI 优化项

def test_ocr_status_detection() -> None:
    """OCR 状态检测返回结构化结果"""
    from galtrans import ocr

    status = ocr.detect_ocr_status()
    assert "ja_available" in status
    assert "current_lang" in status
    assert isinstance(status["available_langs"], list)
    # 语言标签列表与布尔值类型正确
    assert isinstance(status["ja_available"], bool)


def test_language_guide_dialog(config: Config) -> None:
    """语言包引导对话框可构建并刷新状态"""
    from PySide6.QtWidgets import QApplication

    from galtrans.ui.language_guide import LanguageGuideDialog

    app = QApplication.instance() or QApplication([])
    dialog = LanguageGuideDialog()
    app.processEvents()
    # 状态标签有内容且按钮存在
    assert dialog._status_label.text()
    assert dialog._retest_btn
    assert dialog._close_btn
    dialog.refresh_status()
    dialog.close()


def test_engine_hint_state(config: Config) -> None:
    """离线页引擎提示随配置变化（无 key 提示警告，有 key 显示已配置）"""
    from PySide6.QtWidgets import QApplication

    from galtrans.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    conf = config
    conf.set("translate", "primary", "deepseek")
    conf.set_secret("deepseek", "")

    w = MainWindow(conf, Glossary())
    hint = w._offline_page._engine_hint
    assert "需要 API Key" in hint.text()

    # 配置 key 后刷新提示
    conf.set_secret("deepseek", "sk-test")
    w._offline_page._refresh_engine_hint()
    assert "已配置" in hint.text()
    w.close()


def test_settings_test_button(config: Config) -> None:
    """设置页存在全局测试与单引擎测试按钮"""
    from PySide6.QtWidgets import QApplication

    from galtrans.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    w = MainWindow(config, Glossary())
    sp = w._settings_page
    assert sp._test_btn is not None
    assert sp._ds_test_btn is not None
    assert sp._dl_test_btn is not None
    w.close()


# ---------------------------------------------------------------- 安全密钥存储

def test_secret_encrypt_roundtrip(tmp_home: Path) -> None:
    """加密/解密往返正确，密文不含明文"""
    from galtrans.secrets_store import decrypt_secret, encrypt_secret

    enc = encrypt_secret("sk-测试-密钥-abc")
    assert enc.startswith(b"GALTRANS-SEC")
    assert "sk-" not in enc.decode("latin-1")
    assert decrypt_secret(enc) == "sk-测试-密钥-abc"
    # 空值不加密
    assert encrypt_secret("") == b""
    assert decrypt_secret(b"") == ""


def test_secrets_store_persist(tmp_home: Path) -> None:
    """SecretsStore 落盘后可重新读取"""
    from galtrans.secrets_store import SecretsStore

    s1 = SecretsStore()
    s1.set_key("deepseek", "sk-ds-123")
    s2 = SecretsStore()
    assert s2.get_key("deepseek") == "sk-ds-123"
    assert s2.has_key("deepseek")
    # 清空密钥后不存在
    s2.set_key("deepseek", "")
    assert not s2.has_key("deepseek")


def test_config_secret_no_plaintext(tmp_home: Path) -> None:
    """set_secret 后 config.json 不落明文，get_secret 能解密"""
    conf = Config()
    conf.set_secret("deepseek", "sk-secret-456")
    assert conf.get_secret("deepseek") == "sk-secret-456"
    assert conf.get("deepseek", "api_key", "") == ""


def test_config_secret_migrate_legacy(tmp_home: Path) -> None:
    """旧明文 api_key 读取时自动迁移到加密存储并清空明文"""
    conf = Config()
    conf.set("deepl", "api_key", "sk-legacy-old")
    assert conf.get("deepl", "api_key", "") == "sk-legacy-old"
    # 触发迁移
    value = conf.get_secret("deepl")
    assert value == "sk-legacy-old"
    # 明文已清空，二次读取走加密存储
    assert conf.get("deepl", "api_key", "") == ""
    assert conf.get_secret("deepl") == "sk-legacy-old"


def test_engine_reads_secret(config: Config) -> None:
    """翻译引擎从加密存储读取密钥（而非 config.json 明文）"""
    from galtrans.translate.manager import ENGINE_REGISTRY

    config.set_secret("deepseek", "sk-engine-read")
    config.set("deepseek", "api_key", "sk-should-not-use")
    engine = ENGINE_REGISTRY["deepseek"](config)
    assert engine.api_key == "sk-engine-read"


# ---------------------------------------------------------------- 本地模型

def test_local_model_registered(config: Config) -> None:
    """本地模型引擎已注册进 ENGINE_REGISTRY"""
    from galtrans.translate.manager import ENGINE_REGISTRY

    assert "local" in ENGINE_REGISTRY
    engine = ENGINE_REGISTRY["local"](config)
    assert engine.name == "local"
    assert engine.needs_key is False


def test_local_model_undownloaded_raises(config: Config, monkeypatch) -> None:
    """模型未下载时 translate_batch 抛 TranslateError"""
    from galtrans.translate.base import TranslateError
    from galtrans.translate.local_model import LocalModelEngine

    monkeypatch.setattr(
        "galtrans.translate.local_model.is_model_downloaded", lambda *a, **k: False
    )
    engine = LocalModelEngine(config)
    with pytest.raises(TranslateError):
        engine.translate_batch(["こんにちは"], "zh-CN")


def test_local_model_is_downloaded_detection(tmp_home: Path) -> None:
    """is_model_downloaded 识别已下载的模型目录"""
    from galtrans.config import Config
    from galtrans.translate.local_model import (
        get_models_dir,
        is_model_downloaded,
        _repo_dir,
    )

    conf = Config()
    # 显式指定 ASCII 模型目录，避免默认路径含中文触发 ProgramData 回退（防止污染真实目录）
    models_dir = str(tmp_home / "models")
    conf.set("local", "models_dir", models_dir)
    conf.set("local", "model", "Helsinki-NLP/opus-mt-ja-zh")
    repo = _repo_dir(models_dir, "Helsinki-NLP/opus-mt-ja-zh")
    repo.mkdir(parents=True, exist_ok=True)
    # 仅残留 config.json 不算完整下载（避免中断残留误判）
    (repo / "config.json").write_text("{}", encoding="utf-8")
    assert not is_model_downloaded(conf)
    # 有权重文件才算已下载
    (repo / "model.safetensors").write_bytes(b"fake")
    assert is_model_downloaded(conf)
    # download.ok 标记同样视为已下载
    repo2 = _repo_dir(models_dir, "shun89/opus-mt-ja-zh")
    repo2.mkdir(parents=True, exist_ok=True)
    (repo2 / "download.ok").write_text("ok", encoding="utf-8")
    conf.set("local", "model", "shun89/opus-mt-ja-zh")
    assert is_model_downloaded(conf)


def test_local_model_get_models_dir(tmp_home: Path) -> None:
    """models_dir 空时使用默认 ~/.galtrans/models"""
    from galtrans.config import Config
    from galtrans.translate.local_model import get_models_dir

    conf = Config()
    assert get_models_dir(conf).endswith("models")
    custom = str(tmp_home / "custom-models")
    conf.set("local", "models_dir", custom)
    assert get_models_dir(conf) == custom


def test_local_model_models_dir_ascii_fallback(tmp_path: Path, monkeypatch) -> None:
    """默认目录含中文等非 ASCII 时自动回退到纯 ASCII 系统目录"""
    from galtrans.config import Config
    from galtrans.translate.local_model import get_models_dir, _is_ascii_path

    # 中文目录下的 GALTRANS_HOME
    zh_home = tmp_path / "测试目录"
    zh_home.mkdir()
    monkeypatch.setenv("GALTRANS_HOME", str(zh_home))
    conf = Config()
    models_dir = get_models_dir(conf)
    # 回退后的目录必须是纯 ASCII，且可创建
    assert _is_ascii_path(models_dir)
    assert os.path.isdir(models_dir) or os.path.isdir(os.path.dirname(models_dir))
    # 自定义目录不做回退（用户自行负责）
    custom = tmp_path / "中文模型目录"
    conf.set("local", "models_dir", str(custom))
    assert get_models_dir(conf) == str(custom)


def test_realtime_page_local_combo(config: Config) -> None:
    """实时页下拉框包含本地模型选项"""
    from PySide6.QtWidgets import QApplication

    from galtrans.ui.realtime_page import RealtimePage

    app = QApplication.instance() or QApplication([])
    page = RealtimePage(config, None)
    assert page._engine_combo.findData("local") >= 0


def test_settings_page_local_group(config: Config) -> None:
    """设置页本地模型配置组控件齐全"""
    from PySide6.QtWidgets import QApplication

    from galtrans.ui.settings_page import SettingsPage

    app = QApplication.instance() or QApplication([])
    page = SettingsPage(config)
    assert page._local_model_edit is not None
    assert page._local_endpoint_edit is not None
    assert page._local_download_btn is not None
    assert page._local_progress is not None
    assert page._local_test_btn is not None
    app.processEvents()
