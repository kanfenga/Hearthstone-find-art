# -*- coding: utf-8 -*-
"""build_exe.py —— 把查询器打包成单文件 exe（需要 PyInstaller）。

用法（在本目录下打开终端）:
    python -m pip install pyinstaller
    python build_exe.py

产物:
    dist\\炉石原画查询器.exe      单文件，双击即用，无需装 Python
    dist\\hsfinder.exe            同上的英文名副本（方便命令行调用）

说明:
    · 卡名索引 names.json 会被打进 exe，用户查中文名不需要额外下载。
    · 如果没有 names.json，会先尝试用 build_name_index.py 生成。
    · 目标机器无需 Python，也无需联网安装任何东西；查询时才访问 wiki。
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "hsfinder_app.py")
NAMES = os.path.join(HERE, "names.json")
INDEX_BUILDER = os.path.join(HERE, "build_name_index.py")
CN_NAME = "炉石原画查询器"

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except Exception:
            pass


def ensure_index():
    if os.path.exists(NAMES):
        print(f"卡名索引已存在: {NAMES}（{os.path.getsize(NAMES)/1024:.0f} KB）")
        return True
    print("没有 names.json，先生成…")
    if not os.path.exists(INDEX_BUILDER):
        print("[!] 也找不到 build_name_index.py，无法生成索引。")
        return False
    r = subprocess.run([sys.executable, "-X", "utf8", INDEX_BUILDER])
    return r.returncode == 0 and os.path.exists(NAMES)


def ensure_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
        return True
    except ImportError:
        print("[!] 没装 PyInstaller。请先运行：\n"
              f"      {sys.executable} -m pip install pyinstaller")
        return False


def main():
    if not ensure_pyinstaller():
        return 1
    if not ensure_index():
        return 1

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", CN_NAME,
        "--add-data", f"{NAMES}{os.pathsep}.",
        "--exclude-module", "numpy",
        "--exclude-module", "PIL",
        "--exclude-module", "UnityPy",
        APP,
    ]
    print("\n开始打包…\n  " + " \\\n  ".join(cmd[:12]) + " …")
    r = subprocess.run(cmd, cwd=HERE)
    if r.returncode != 0:
        print("\n[!] 打包失败。把上面的报错发给我。")
        return r.returncode

    dist = os.path.join(HERE, "dist")
    exe = os.path.join(dist, f"{CN_NAME}.exe")
    if not os.path.exists(exe):
        print(f"[!] 没找到产物 {exe}")
        return 1
    # 再复制一份英文名，方便命令行敲
    try:
        shutil.copy2(exe, os.path.join(dist, "hsfinder.exe"))
    except Exception as e:
        print(f"[i] 英文名副本没做成：{e}")

    size = os.path.getsize(exe) / 1048576
    print(f"\n完成：{exe}（{size:.1f} MB）")
    print("把这个 exe 发给别人，双击就能用，对方不需要装 Python。")
    print("\n提示：exe 首次启动要解压自身，约需 1~3 秒，属正常现象。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
