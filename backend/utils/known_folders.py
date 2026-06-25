"""
Windows 已知目录获取 —— 通过 SHGetKnownFolderPath (pywin32 / ctypes 降级)。
"""
import ctypes
from pathlib import Path
from ctypes import wintypes


# ---------------------------------------------------------------------------
# KNOWNFOLDERID GUID 常量（Windows Vista+）
# ---------------------------------------------------------------------------
# 来源: https://docs.microsoft.com/en-us/windows/win32/shell/knownfolderid

_KNOWN_FOLDER_GUIDS: dict[str, str] = {
    "Desktop":   "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
    "Downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
    "Documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
    "Pictures":  "{33E28130-4E1E-4676-835A-98395C3BC3BB}",
    "Music":     "{4BD8D571-6D19-48D3-BE97-422220080E43}",
    "Videos":    "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}",
}


# ---------------------------------------------------------------------------
# 方案 1：pywin32（优先）
# ---------------------------------------------------------------------------

def _get_folder_pywin32(folder_name: str) -> str | None:
    """通过 pywin32 获取已知目录路径。"""
    try:
        from win32com.shell import shell, shellcon  # type: ignore
    except ImportError:
        return None

    # pywin32 映射（部分文件夹有内置常量）
    const_map = {
        "Desktop":   shellcon.CSIDL_DESKTOP,
        "Downloads": None,  # pywin32 没有直接常量，降级 ctypes
        "Documents": shellcon.CSIDL_PERSONAL,
        "Pictures":  shellcon.CSIDL_MYPICTURES,
        "Music":     shellcon.CSIDL_MYMUSIC,
        "Videos":    shellcon.CSIDL_MYVIDEO,
    }

    const = const_map.get(folder_name)
    if const is not None:
        return shell.SHGetFolderPath(0, const, 0, 0)
    return None


# ---------------------------------------------------------------------------
# 方案 2：ctypes（降级方案）
# ---------------------------------------------------------------------------

def _get_folder_ctypes(folder_name: str) -> str | None:
    """通过 ctypes 调用 SHGetKnownFolderPath 获取路径。"""
    guid_str = _KNOWN_FOLDER_GUIDS.get(folder_name)
    if guid_str is None:
        return None

    try:
        shell32 = ctypes.windll.shell32
    except AttributeError:
        return None

    # GUID 结构
    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", wintypes.BYTE * 8),
        ]

    # 解析 GUID 字符串
    import uuid
    g = uuid.UUID(guid_str)
    guid = GUID()
    guid.Data1 = g.time_low
    guid.Data2 = g.time_mid
    guid.Data3 = g.time_hi_version
    guid.Data4 = (wintypes.BYTE * 8)(*list(g.clock_seq_hi_variant.to_bytes(1, 'big') + g.clock_seq_low.to_bytes(1, 'big') + g.node.to_bytes(6, 'big')))

    # SHGetKnownFolderPath
    psz_path = wintypes.LPWSTR()
    KF_FLAG_DEFAULT = 0x00000000

    ret = shell32.SHGetKnownFolderPath(
        ctypes.byref(guid), KF_FLAG_DEFAULT, None, ctypes.byref(psz_path)
    )

    if ret == 0:  # S_OK
        result = psz_path.value
        ctypes.windll.ole32.CoTaskMemFree(psz_path)
        return result

    return None


# ---------------------------------------------------------------------------
# 统一接口
# ---------------------------------------------------------------------------

def get_known_folder(folder_name: str) -> Path:
    """
    获取 Windows 已知目录的绝对路径。
    优先使用 pywin32，失败时降级到 ctypes。

    folder_name 取值: "Desktop" | "Downloads" | "Documents" |
                      "Pictures" | "Music" | "Videos"
    """
    if folder_name not in _KNOWN_FOLDER_GUIDS:
        raise ValueError(
            f"Unknown folder: '{folder_name}'. "
            f"Valid: {', '.join(_KNOWN_FOLDER_GUIDS.keys())}"
        )

    path_str = _get_folder_pywin32(folder_name)
    if path_str is None:
        path_str = _get_folder_ctypes(folder_name)
    if path_str is None:
        raise OSError(
            f"Cannot resolve known folder: '{folder_name}'. "
            f"Neither pywin32 nor ctypes fallback succeeded."
        )

    return Path(path_str)


def get_all_known_folders() -> dict[str, Path]:
    """获取所有支持的已知目录 -> 路径映射。"""
    result: dict[str, Path] = {}
    for name in _KNOWN_FOLDER_GUIDS:
        result[name] = get_known_folder(name)
    return result
