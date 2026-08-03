"""API Key 安全存储模块

使用 Windows DPAPI（CryptProtectData/CryptUnprotectData）对 API Key
进行加密，仅当前 Windows 用户可解密。密文独立存放于配置目录下的
secrets.bin，避免 API Key 以明文写入 config.json。

非 Windows 平台降级为明文（开发/测试用途），并打印警告。
"""
from __future__ import annotations

import ctypes
import sys
import warnings
from ctypes import wintypes
from pathlib import Path

# 密文文件头，用于识别加密格式
_MAGIC = b"GALTRANS-SEC\x00\x01"


class DATA_BLOB(ctypes.Structure):
    """Win32 DATA_BLOB 结构"""

    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def _crypt32() -> bool:
    """初始化 crypt32 函数原型（Windows 平台）"""
    if sys.platform != "win32":
        return False
    try:
        _crypt32_api()
        return True
    except (AttributeError, OSError):
        return False


def _crypt32_api():
    """定义并返回 crypt32 API 句柄（惰性加载）"""
    crypt32 = ctypes.windll.crypt32
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        wintypes.LPCWSTR,
        ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(DATA_BLOB),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        ctypes.POINTER(wintypes.LPCWSTR),
        ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(DATA_BLOB),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    return crypt32


def _local_free(ptr) -> None:
    """释放 DPAPI 分配的内存"""
    if ptr:
        ctypes.windll.kernel32.LocalFree(ptr)


def _blob_from_bytes(data: bytes) -> DATA_BLOB:
    """将字节串封装为 DATA_BLOB"""
    buf = ctypes.create_string_buffer(data, len(data))
    return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))


def _protect(data: bytes) -> bytes:
    """使用 DPAPI 加密字节串"""
    crypt32 = _crypt32_api()
    in_blob = _blob_from_bytes(data)
    out_blob = DATA_BLOB()
    ok = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "galtrans",
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise OSError("CryptProtectData 加密失败")
    try:
        return bytes(ctypes.string_at(out_blob.pbData, out_blob.cbData))
    finally:
        _local_free(out_blob.pbData)


def _unprotect(data: bytes) -> bytes:
    """使用 DPAPI 解密字节串"""
    crypt32 = _crypt32_api()
    in_blob = _blob_from_bytes(data)
    out_blob = DATA_BLOB()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise OSError("CryptUnprotectData 解密失败")
    try:
        return bytes(ctypes.string_at(out_blob.pbData, out_blob.cbData))
    finally:
        _local_free(out_blob.pbData)


def encrypt_secret(value: str) -> bytes:
    """加密一个字符串，返回带标记头的密文字节。

    参数:
        value: 待加密的明文（如 API Key）。
    返回:
        密文字节（含头标记，可安全写入文件）。
    """
    if not value:
        return b""
    payload = value.encode("utf-8")
    if sys.platform == "win32" and _crypt32():
        return _MAGIC + _protect(payload)
    # 非 Windows 或 DPAPI 不可用时降级明文（仅测试/开发）
    warnings.warn("DPAPI 不可用，密钥将以明文存储（仅限开发测试环境）")
    return _MAGIC + b"PLAIN:" + payload


def decrypt_secret(data: bytes) -> str:
    """解密 encrypt_secret 产生的密文，返回明文。

    参数:
        data: 密文字节；空字节返回空串。
    返回:
        解密后的明文字符串。
    """
    if not data:
        return ""
    if not data.startswith(_MAGIC):
        return data.decode("utf-8", errors="replace")
    payload = data[len(_MAGIC):]
    if payload.startswith(b"PLAIN:"):
        return payload[len(b"PLAIN:"):].decode("utf-8", errors="replace")
    return _unprotect(payload).decode("utf-8", errors="replace")


class SecretsStore:
    """管理所有 API Key 的加密持久化。

    存储格式：JSON，形如 {"deepseek": "<密文>", "deepl": "<密文>"}。
    文件权限设为仅当前用户可读写（Windows 上尽力而为）。
    """

    def __init__(self, path: Path | None = None) -> None:
        from .config import get_config_dir

        self._path = path or (get_config_dir() / "secrets.json")
        self._data: dict = self._load()

    def _load(self) -> dict:
        """从磁盘加载密文映射（容忍文件损坏）"""
        if not self._path.exists():
            return {}
        try:
            import json

            with open(self._path, encoding="utf-8") as fp:
                return json.load(fp)
        except (json.JSONDecodeError, OSError):
            return {}

    def save(self) -> None:
        """持久化密文映射到磁盘"""
        import json

        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as fp:
            json.dump(self._data, fp, ensure_ascii=False, indent=2)
        self._restrict_permissions()

    def _restrict_permissions(self) -> None:
        """限制文件权限为当前用户（Windows 用 icacls，失败静默）"""
        if sys.platform != "win32":
            return
        try:
            import os
            import subprocess

            user = os.environ.get("USERNAME", "")
            if not user:
                return
            subprocess.run(
                ["icacls", str(self._path), "/inheritance:r", "/grant:r", f"{user}:F"],
                capture_output=True,
                check=False,
            )
        except Exception:  # noqa: BLE001
            pass

    def set_key(self, name: str, value: str) -> None:
        """加密保存某个服务的 API Key"""
        if value:
            self._data[name] = encrypt_secret(value).decode("latin-1")
        else:
            self._data.pop(name, None)
        self.save()

    def get_key(self, name: str) -> str:
        """读取某个服务的 API Key（解密），不存在返回空串"""
        raw = self._data.get(name, "")
        if not raw:
            return ""
        try:
            return decrypt_secret(raw.encode("latin-1"))
        except OSError:
            return ""

    def has_key(self, name: str) -> bool:
        """判断某服务是否已保存 API Key"""
        return bool(self.get_key(name))
