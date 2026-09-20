# -*- coding: utf-8 -*-
"""build_exe.py —— 打包成单文件 exe（需要 PyInstaller）。

用法（在本目录下打开终端）:

    python -m pip install pyinstaller
    python build_exe.py                 # 生成 dist/炉石原画查询器.exe
    python build_exe.py --onedir        # 生成目录版（启动更快，但是一个文件夹）

产物:
    dist\\炉石原画查询器.exe     单文件，双击即用，无需装 Python
    dist\\hsfinder.exe           同上的英文名副本（方便命令行调用）

说明:
    · 卡名索引 hsfinder\\names.json 会被打进 exe，查中文名不需要额外下载；
    · Pillow 若已安装会被自动带上（预览画质更好）；没装也能用，
      程序会退回系统自带的 GDI+ 解码；
    · 目标机器无需 Python、无需联网安装任何东西，只有查询时才访问 wiki。
"""
import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENTRY = os.path.join(HERE, "hsfinder_app.py")
PKG_DIR = os.path.join(HERE, "hsfinder")
INDEX = os.path.join(PKG_DIR, "names.json")
ICON = os.path.join(HERE, "icon.ico")
INDEX_BUILDER = os.path.join(HERE, "build_name_index.py")
CN_NAME = "炉石原画查询器"

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except Exception:
            pass


def ensure_index():
    if os.path.exists(INDEX):
        print(f"卡名索引已存在: {INDEX}（{os.path.getsize(INDEX)/1024:.0f} KB）")
        return True
    print("没有 names.json，先生成…")
    if not os.path.exists(INDEX_BUILDER):
        print("[!] 也找不到 build_name_index.py，无法生成索引。")
        return False
    ok = subprocess.run([sys.executable, "-X", "utf8", INDEX_BUILDER, "--fetch"],
                        cwd=HERE).returncode == 0
    return ok and os.path.exists(INDEX)


def ensure_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
        return True
    except ImportError:
        print("[!] 没装 PyInstaller。请先运行：\n"
              f"      {sys.executable} -m pip install pyinstaller")
        return False


def build(onefile=True):
    mode = "--onefile" if onefile else "--onedir"
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", mode, "--windowed",
        "--name", CN_NAME,
        "--add-data", f"{INDEX}{os.pathsep}hsfinder",
        "--collect-submodules", "PIL",
        "--exclude-module", "numpy",
        "--exclude-module", "UnityPy",
        "--exclude-module", "matplotlib",
        "--exclude-module", "pytest",
    ]
    if os.path.exists(ICON):
        cmd += ["--icon", ICON]
    cmd.append(ENTRY)

    print("\n开始打包（可能要一两分钟）…\n")
    r = subprocess.run(cmd, cwd=HERE)
    if r.returncode != 0:
        print("\n[!] 打包失败。把上面的报错发给我。")
        return r.returncode

    dist = os.path.join(HERE, "dist")
    exe = os.path.join(dist, f"{CN_NAME}.exe")
    if not os.path.exists(exe):
        print(f"[!] 没找到产物 {exe}")
        return 1
    try:
        shutil.copy2(exe, os.path.join(dist, "hsfinder.exe"))
    except Exception as e:
        print(f"[i] 英文名副本没做成：{e}")

    size = os.path.getsize(exe) / 1048576
    print(f"\n完成：{exe}（{size:.1f} MB）")
    print("把这个 exe 发给别人，双击就能用，对方不需要装 Python。")
    if onefile:
        print("\n提示：单文件版首次启动要解压自身，约需 1~3 秒，属正常现象。")
    else:
        print("\n提示：目录版要把整个 dist 文件夹一起发，启动更快。")
    return 0


def main():
    ap = argparse.ArgumentParser(description="把查询器打包成 exe")
    ap.add_argument("--onedir", action="store_true",
                    help="生成目录版（启动更快，但要整个文件夹一起发）")
    args = ap.parse_args()

    if not ensure_pyinstaller():
        return 1
    if not ensure_index():
        return 1
    return build(onefile=not args.onedir)


if __name__ == "__main__":
    sys.exit(main())
