# -*- coding: utf-8 -*-
"""原画预览面板。

只负责「显示」：图片字节由外部通过回调提供（网络在 app 层做），
这样面板本身可以独立测试，也不依赖 core 的网络部分。

两条渲染路径：
- 有 Pillow：``ImageTk`` 显示，缩放质量最好；
- 没有 Pillow：走 ``core.images.GdiPlus``，零依赖。
"""
import tkinter as tk

from .theme import Colors, Fonts, Space
from .widgets import hex_blend

TAB_KEYS = (("regular", "普通版"), ("signature", "异画"))


class PreviewPanel(tk.Frame):
    def __init__(self, master, fonts=None, fetch=None):
        """``fetch(url, ticket)`` 由外部实现：取到字节后回调 ``set_image``。"""
        self.fonts = fonts or Fonts()
        self._fetch = fetch
        super().__init__(master, bg=Colors.surface, highlightthickness=1,
                         highlightbackground=Colors.border, bd=0)

        # -- 顶部：标题 + 正/异画切换 --------------------------------------
        head = tk.Frame(self, bg=Colors.surface)
        head.pack(fill="x", padx=Space.md, pady=(Space.md, Space.xs))
        self.title = tk.Label(head, text="原画预览", bg=Colors.surface,
                              fg=Colors.text_muted, font=self.fonts.small("bold"))
        self.title.pack(side="left")

        self.tabs = {}
        tabbar = tk.Frame(head, bg=Colors.surface)
        tabbar.pack(side="right")
        for key, text in reversed(TAB_KEYS):        # 逆序 pack 让顺序自然
            btn = tk.Label(tabbar, text=text, bg=Colors.surface,
                           fg=Colors.text_muted, font=self.fonts.small(),
                           padx=Space.sm + 2, pady=2, cursor="hand2")
            btn.pack(side="right", padx=(Space.xs, 0))
            btn.bind("<Button-1>", lambda e, k=key: self.select_tab(k))
            self.tabs[key] = btn

        # -- 图片区：固定尺寸容器 + 关闭几何传播 ---------------------------
        # 否则图片会把控件反向撑大，「铺满宽度」就无从谈起
        self.holder = tk.Frame(self, bg=Colors.surface_alt,
                               highlightthickness=1,
                               highlightbackground=Colors.border)
        self.holder.pack(fill="both", expand=True, padx=Space.md, pady=(0, Space.xs))
        self.holder.pack_propagate(False)
        self.image_label = tk.Label(self.holder, text="查询后这里显示原画",
                                    bg=Colors.surface_alt, fg=Colors.text_faint,
                                    font=self.fonts.small(), anchor="center",
                                    justify="center")
        self.image_label.pack(fill="both", expand=True)
        self.holder.bind("<Configure>", self._on_resize)

        # -- 底部：尺寸说明 ------------------------------------------------
        self.caption = tk.Label(self, text="", bg=Colors.surface,
                                fg=Colors.text_faint, font=self.fonts.caption(),
                                anchor="center", justify="center")
        self.caption.pack(fill="x", padx=Space.md, pady=(0, Space.md))

        # -- 状态 ----------------------------------------------------------
        self._images = {}          # {tag: 图片信息 dict}
        self._active = "regular"
        self._bytes = None         # 当前标签页的原始字节
        self._photo = None         # 持有的 PhotoImage（必须留引用）
        self._meta = (None, None)
        self._ticket = 0
        self._last_width = 0
        self._resize_job = None
        self._refresh_tabs()

    # -- 对外接口 -----------------------------------------------------------
    def show(self, images, prefer=None):
        """显示一组原画。``images`` 形如 ``{"regular": {...} or None, ...}``。"""
        self._images = images or {}
        available = [k for k, _ in TAB_KEYS if self._images.get(k)]
        if prefer and self._images.get(prefer):
            self._active = prefer
        elif self._active not in available:
            self._active = available[0] if available else "regular"
        self._refresh_tabs()
        self._load_active()

    def clear(self, message="查询后这里显示原画"):
        self._ticket += 1
        self._images = {}
        self._bytes = None
        self._photo = None
        self._meta = (None, None)
        self.image_label.configure(image="", text=message)
        self.caption.configure(text="")
        self._refresh_tabs()

    def select_tab(self, key):
        if key == self._active and self._bytes:
            return
        self._active = key
        self._refresh_tabs()
        self._load_active()

    # -- 内部 ---------------------------------------------------------------
    def _refresh_tabs(self):
        for key, btn in self.tabs.items():
            has = bool(self._images.get(key))
            active = (key == self._active)
            if not has:
                btn.configure(fg=Colors.text_faint, bg=Colors.surface,
                              cursor="arrow")
                continue
            btn.configure(cursor="hand2",
                          fg=Colors.primary if active else Colors.text_muted,
                          bg=Colors.surface)
            # 选中项加下划线质感：用淡色底衬托
            btn.configure(bg=Colors.primary_soft if active else Colors.surface,
                          padx=Space.sm + 2)

    def _load_active(self):
        info = self._images.get(self._active)
        self._bytes = None
        self._photo = None
        if not info or not info.get("url"):
            self.image_label.configure(image="", text="wiki 未收录这张原画")
            self.caption.configure(text="")
            return
        self._meta = (info.get("width"), info.get("height"))
        self.image_label.configure(image="", text="正在载入…")
        self.caption.configure(text="")
        self._ticket += 1
        if self._fetch:
            self._fetch(info["url"], self._ticket)

    def set_image(self, ticket, data):
        """外部取到字节后调用。``data=None`` 表示失败。"""
        if ticket != self._ticket:
            return                                  # 已经切到别的图，丢弃
        if data is None:
            self.image_label.configure(image="", text="这张预览取不到")
            self.caption.configure(text="可点右侧链接在浏览器打开原图")
            return
        self._bytes = data
        # 布局此刻可能还没算完，等一拍再按真实宽度缩放
        self.after_idle(self.render)

    def _on_resize(self, event):
        if not self._bytes:
            return
        if abs(event.width - self._last_width) < 3:
            return
        if self._resize_job is not None:
            try:
                self.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.after(150, self.render)

    def box(self):
        """图片可用尺寸：宽度优先（图片铺满容器宽度，高度按比例）。"""
        bw = self.holder.winfo_width()
        bh = self.holder.winfo_height()
        if bw <= 1:
            bw = max(220, self.image_label.winfo_reqwidth())
        box_w = max(80, bw - 2)
        want_h = int(box_w * 1.6) + Space.sm
        if bh <= 1:
            bh = want_h
        return box_w, max(want_h, bh)

    def render(self):
        """按当前容器宽度把图片铺满并显示。"""
        if not self._bytes:
            return
        box_w, box_h = self.box()
        self._last_width = box_w
        ow, oh = self._meta
        try:
            photo, fw, fh = self._make_photo(box_w, box_h)
            if photo is None:
                raise RuntimeError("无法解码这张图片")
            self._photo = photo                       # 必须留引用，否则被回收
            self.image_label.configure(image=photo, text="")
            self.caption.configure(text=f"原图 {ow}×{oh}    显示 {fw}×{fh}")
        except Exception as e:
            self.image_label.configure(image="", text=f"预览失败：{e}")
            self.caption.configure(text="")

    def _make_photo(self, box_w, box_h):
        """生成 PhotoImage，返回 ``(photo, 宽, 高)``。"""
        from ..core import images as img
        # 路径 1：Pillow
        pil = img.decode_pil(self._bytes)
        if pil is not None:
            fitted = img.fit_pil(pil, box_w, box_h)
            photo = img.pil_to_photoimage(fitted)
            if photo is not None:
                return photo, fitted.size[0], fitted.size[1]
        # 路径 2：系统 GDI+（零依赖）
        gp = img.GdiPlus.get()
        if gp is not None and gp.available:
            b64 = gp.load_scaled_png(self._bytes, box_w, box_h)
            if b64:
                photo = tk.PhotoImage(data=b64)
                return photo, photo.width(), photo.height()
        return None, 0, 0


__all__ = ["PreviewPanel", "TAB_KEYS"]
