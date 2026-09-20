# -*- coding: utf-8 -*-
"""设计令牌：颜色、字体、间距、圆角。

界面代码只引用这里的名字，不写死颜色和像素值 —— 这样换风格只改一处，
也能保证各处的间距和层级是一致的。

字体可用性会**运行时探测**：不假设用户的机器装了什么字体，
按候选项依次找一个真正存在的，全都找不到就退回 Tk 默认。
"""
import tkinter as tk
from tkinter import font as tkfont


# ---------------------------------------------------------------------------
# 颜色
# ---------------------------------------------------------------------------
class Colors:
    # 背景层
    bg = "#f2f4f7"            # 窗口底色
    surface = "#ffffff"       # 卡片 / 面板
    surface_alt = "#f8fafc"   # 次级面板（如预览底衬）
    border = "#e2e6ec"        # 分隔线
    border_strong = "#cfd6df"

    # 文字
    text = "#101828"          # 主文字
    text_muted = "#667085"    # 次要说明
    text_faint = "#98a2b3"    # 占位 / 弱提示
    text_inverse = "#ffffff"

    # 主色
    primary = "#2f6feb"
    primary_hover = "#1f5bd0"
    primary_soft = "#eaf1ff"

    # 语义色
    success = "#079455"
    warning = "#b54708"
    danger = "#d92d20"

    # 交互
    hover = "#f2f4f7"
    focus = "#2f6feb"


# ---------------------------------------------------------------------------
# 间距与圆角（8 的倍数体系，外加少量 4 的倍数）
# ---------------------------------------------------------------------------
class Space:
    xs = 4
    sm = 8
    md = 12
    lg = 16
    xl = 24
    xxl = 32


class Radius:
    sm = 6
    md = 10
    lg = 14


# ---------------------------------------------------------------------------
# 字体：运行时探测
# ---------------------------------------------------------------------------
_UI_CANDIDATES = [
    "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC",
    "Source Han Sans SC", "WenQuanYi Micro Hei", "SimHei", "SimSun",
    "Segoe UI", "Helvetica Neue", "Helvetica", "Arial",
]
_MONO_CANDIDATES = ["Cascadia Mono", "Consolas", "Menlo", "DejaVu Sans Mono",
                    "Courier New"]


def _pick_font(candidates, available):
    for name in candidates:
        if name in available:
            return name
    return None


class Fonts:
    """字体族与字号。实例化时需要 Tk root 已存在。"""

    def __init__(self):
        self.family = None
        self.mono = None
        try:
            available = set(tkfont.families())
            self.family = _pick_font(_UI_CANDIDATES, available) or "TkDefaultFont"
            self.mono = _pick_font(_MONO_CANDIDATES, available) or "TkFixedFont"
            self.scale = _dpi_scale()
        except Exception:
            self.family = "TkDefaultFont"
            self.mono = "TkFixedFont"
            self.scale = 1.0

        s = self.scale

        def px(n):
            return max(7, int(round(n * s)))

        self.size_caption = px(9)
        self.size_small = px(10)
        self.size_body = px(11)
        self.size_subtitle = px(13)
        self.size_title = px(18)
        self.size_hero = px(22)

    # 便捷构造 -------------------------------------------------------------
    def f(self, size, weight="normal"):
        return (self.family, size, weight)

    def body(self, weight="normal"):
        return self.f(self.size_body, weight)

    def small(self, weight="normal"):
        return self.f(self.size_small, weight)

    def caption(self):
        return self.f(self.size_caption)

    def subtitle(self, weight="bold"):
        return self.f(self.size_subtitle, weight)

    def title(self, weight="bold"):
        return self.f(self.size_title, weight)

    def hero(self, weight="bold"):
        return self.f(self.size_hero, weight)

    def mono_small(self):
        return (self.mono, self.size_caption)


def _dpi_scale():
    """返回界面缩放系数（1.0 表示 96 DPI）。

    没有缩放的话，在高分屏上字会很小。优先用 Tk 自己的缩放，
    它已经综合了系统 DPI 设置。
    """
    try:
        root = tk._default_root
        if root is not None:
            return max(1.0, float(root.tk.call("tk", "scaling")) / 1.3333)
    except Exception:
        pass
    try:
        import ctypes
        dc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(dc, 88)   # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, dc)
        if dpi:
            return max(1.0, dpi / 96.0)
    except Exception:
        pass
    return 1.0


def enable_dpi_awareness():
    """让 Windows 按真实 DPI 渲染，否则高分屏上字会发虚。

    必须在创建 Tk 窗口之前调用。失败无所谓，只是显示略微模糊。
    """
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)   # PROCESS_SYSTEM_DPI_AWARE
        return
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


__all__ = ["Colors", "Space", "Radius", "Fonts", "enable_dpi_awareness"]
