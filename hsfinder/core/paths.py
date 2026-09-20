# -*- coding: utf-8 -*-
"""路径解析 —— 保证程序在任何机器、任何安装方式下都能找到自己的文件。

需要同时应付三种运行方式：
1. 源码运行（``python hsfinder_app.py``）：文件就在仓库里；
2. 打包成单文件 exe：资源被解到 ``sys._MEIPASS`` 临时目录；
3. 打包成目录版 exe / 装在只读位置：可写数据必须另找地方。

原则：**只读资源**从程序自身位置找，**可写数据**放用户目录，
并且每一层都留了回退，任何一步失败都不会让程序起不来。
"""
import os
import sys

from ..meta import CACHE_FOLDER


def app_dir():
    """程序所在目录（打包后是 exe 所在目录，源码运行时是仓库根目录）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    # core/paths.py -> core -> hsfinder（包目录） -> 仓库根
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def package_dir():
    """包目录 ``hsfinder/``，随包分发只读资源（如 names.json）放这里。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(name):
    """定位随程序分发的只读资源。

    依次尝试：打包临时目录 → 包目录 → 仓库根目录。
    最后一个是为了兼容旧版本把 names.json 放在仓库根的情形。
    """
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, name))          # exe 解出的根
        candidates.append(os.path.join(meipass, "hsfinder", name))
    candidates.append(os.path.join(package_dir(), name))
    candidates.append(os.path.join(app_dir(), name))
    for path in candidates:
        if os.path.exists(path):
            return path
    # 都不存在也返回首选路径，让调用方给出「文件缺失」的明确提示
    return candidates[0] if candidates else name


def _writable(path):
    """目录是否可写（真去建个临时文件试一下，比看权限位可靠）。"""
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write_probe")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("x")
        os.remove(probe)
        return True
    except Exception:
        return False


def cache_dir():
    """可写的缓存目录。

    优先用户数据目录（Windows 是 %LOCALAPPDATA%），
    可用环境变量 ``HSFINDER_CACHE`` 覆盖（便携用法：指到 U 盘），
    都不行时退回程序目录 —— 只读位置下也不至于崩，只是缓存不生效。
    """
    override = os.environ.get("HSFINDER_CACHE")
    if override and _writable(override):
        return override

    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".cache")
    preferred = os.path.join(base, CACHE_FOLDER)
    if _writable(preferred):
        return preferred

    fallback = os.path.join(app_dir(), "cache")
    if _writable(fallback):
        return fallback

    # 彻底不可写：返回首选路径，后续写操作会失败但程序仍可查询
    return preferred


def cache_file():
    from ..config import CACHE_FILE
    return os.path.join(cache_dir(), CACHE_FILE)


__all__ = ["app_dir", "package_dir", "resource_path", "cache_dir", "cache_file"]
