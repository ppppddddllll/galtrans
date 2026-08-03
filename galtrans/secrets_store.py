"""API Key 安全存储：Windows DPAPI 加密（无第三方依赖）。

非 Windows 或 DPAPI 不可用时降级为明文标记存储（开发/测试环境）。
"""
from __future__ import annotations

import ctypes
import json
import os
import warnings
from ctypes import wintypes
from pathlib import Path

# 密文魔数前缀，用于识别本工具生成的密文
_MAGIC = b"GALTRANS-SEC\x00\x01"


class DATA_BLOB(ctypes.Structure):
    """Windows CryptProtectData 使用的二进制块结构。"""

    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob_from_bytes(data: bytes) -> DATA_BLOB:
    """把 bytes 包装成 DATA_BLOB。"""
    buf = ctypes.create_string_buffer(data, len(data))
    return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def _local_free(ptr) -> None:
    """释放 CryptProtectData 分配的内存（注意在 kernel32）。"""
    try:
        ctypes.windll.kernel32.LocalFree(ptr)
    except Exception:  # noqa: BLE001
        pass


def _protect(data: bytes) -> bytes:
    """调用 CryptProtectData 加密。"""
    from ctypes import byref

    blob_in = _blob_from_bytes(data)
    blob_out = DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptProtectData(
        byref(blob_in), None, None, None, None, 0, byref(blob_out)
    )
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        _local_free(blob_out.pbData)


def _unprotect(data: bytes) -> bytes:
    """调用 CryptUnprotectData 解密。"""
    from ctypes import byref

    blob_in = _blob_from_bytes(data)
    blob_out = DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        byref(blob_in), None, None, None, None, 0, byref(blob_out)
    )
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        _local_free(blob_out.pbData)


def _dpapi_available() -> bool:
    """判断当前是否为可用的 Windows DPAPI 环境。"""
    return os.name == "nt" and hasattr(ctypes, "windll") and hasattr(ctypes.windll, "crypt32")


def encrypt_secret(value: str) -> bytes:
    """加密字符串，返回密文 bytes。空串返回 b""。"""
    if not value:
        return b""
    payload = value.encode("utf-8")
    if _dpapi_available():
        try:
            return _MAGIC + _protect(payload)
        except Exception:  # noqa: BLE001
            warnings.warn("DPAPI 加密失败，降级为明文存储。", stacklevel=2)
    return _MAGIC + b"PLAIN:" + payload


def decrypt_secret(data: bytes) -> str:
    """解密 bytes，返回字符串。"""
    if not data:
        return ""
    if not data.startswith(_MAGIC):
        return data.decode("utf-8", errors="replace")
    payload = data[len(_MAGIC):]
    if payload.startswith(b"PLAIN:"):
        return payload[len(b"PLAIN:"):].decode("utf-8", errors="replace")
    try:
        return _unprotect(payload).decode("utf-8", errors="replace")
    except OSError:
        return ""


class SecretsStore:
    """密钥持久化存储（JSON + DPAPI）。"""

    def __init__(self, path: Path | None = None) -> None:
        from .config import get_config_dir

        self._path = path or (get_config_dir() / "secrets.json")
        self._data: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        """从磁盘加载密钥字典。"""
        if not self._path.exists():
            return
        try:
            with open(self._path, encoding="utf-8") as fp:
                raw = json.load(fp)
            if isinstance(raw, dict):
                self._data = {k: str(v) for k, v in raw.items()}
        except (json.JSONDecodeError, OSError):
            self._data = {}

    def _save(self) -> None:
        """持久化到磁盘，并限制文件权限（仅当前用户）。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as fp:
            json.dump(self._data, fp, ensure_ascii=False, indent=2)
        self._restrict_permissions()

    def _restrict_permissions(self) -> None:
        """用 icacls 把密钥文件改为仅当前用户可读写（失败静默）。"""
        if os.name != "nt":
            return
        try:
            import subprocess

            user = os.environ.get("USERNAME", "")
            if user:
                subprocess.run(
                    ["icacls", str(self._path), "/inheritance:r", f"/grant:r {user}:F"],
                    capture_output=True,
                    timeout=10,
                )
        except Exception:  # noqa: BLE001
            pass

    def set_key(self, name: str, value: str) -> None:
        """写入密钥；空值则删除。"""
        if not value:
            self._data.pop(name, None)
        else:
            self._data[name] = encrypt_secret(value).decode("latin-1")
        self._save()

    def get_key(self, name: str) -> str:
        """读取密钥，缺失或解密失败返回空串。"""
        raw = self._data.get(name, "")
        if not raw:
            return ""
        try:
            return decrypt_secret(raw.encode("latin-1"))
        except OSError:
            return ""

    def has_key(self, name: str) -> bool:
        """判断是否存在有效密钥。"""
        return bool(self.get_key(name))
