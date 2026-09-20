#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""炉石原画查询器 —— 启动入口。

真正的实现都在 ``hsfinder/`` 包里，这个文件只做两件事：

1. 修正命令行参数（Windows 下 pythonw 会按 ANSI 代码页解中文参数，
   双击运行时还会把脚本路径塞进来）；
2. 启动图形界面。

命令行用法::

    python hsfinder_app.py                 # 打开窗口
    python hsfinder_app.py 时空大盗拉法姆   # 打开并直接查询
    python hsfinder_app.py --version       # 只看版本
"""
import os
import sys

# 允许从任意目录运行（双击 / 快捷方式 / 打包）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _repair_argv():
    """修掉中文参数乱码，并丢弃「双击运行时被塞进来的脚本路径」。"""
    out = []
    for i, arg in enumerate(sys.argv):
        if i == 0:
            continue
        # 双击 .py 时 argv[1] 是脚本自身路径
        if i == 1 and not out and arg.lower().endswith((".py", ".pyw", ".exe")):
            base = os.path.basename(arg).lower()
            if base == os.path.basename(sys.argv[0]).lower() or "hsfinder" in base:
                continue
        # 乱码修复：正确的 UTF-8 被按 ANSI 代码页解读过，
        # 那么按 ANSI 编码回去、再按 UTF-8 解出来即可还原
        if any(ord(ch) > 127 for ch in arg):
            for enc in ("cp936", "mbcs", "cp1252"):
                try:
                    fixed = arg.encode(enc).decode("utf-8")
                except Exception:
                    continue
                if fixed != arg and any(ord(ch) > 127 for ch in fixed):
                    arg = fixed
                    break
        out.append(arg)
    return out


CLI_ARGS = _repair_argv()


def main():
    from hsfinder import VERSION, run
    if any(a in ("-V", "--version") for a in CLI_ARGS):
        print(f"hsfinder {VERSION}")
        return 0
    if any(a in ("-h", "--help") for a in CLI_ARGS):
        print(__doc__)
        return 0

    # 排查用：设了 HSFINDER_ARGLOG 就把实际收到的参数写出去
    log_path = os.environ.get("HSFINDER_ARGLOG")
    if log_path:
        try:
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(repr(CLI_ARGS))
        except Exception:
            pass

    return run(CLI_ARGS)


if __name__ == "__main__":
    sys.exit(main())
