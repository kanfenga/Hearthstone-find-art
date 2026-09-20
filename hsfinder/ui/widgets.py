# -*- coding: utf-8 -*-
"""可复用控件。

tkinter 原生控件外观老旧，这里用 Frame + Label 组合出统一风格的
卡片、按钮、链接等，并提供悬停 / 聚焦反馈。所有颜色和字体都取自 theme。
"""
import tkinter as tk

from .theme import Colors, Fonts, Radius, Space


def hex_blend(c1, c2, ratio):
    """两个 #rrggbb 之间插值，ratio=0 取 c1。用于生成悬停色。"""
    def parts(c):
        c = c.lstrip("#")
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    a, b = parts(c1), parts(c2)
    mixed = tuple(round(a[i] + (b[i] - a[i]) * ratio) for i in range(3))
    return "#%02x%02x%02x" % mixed


class Card(tk.Frame):
    """带细边框的白色面板。"""

    def __init__(self, master, padding=Space.lg, bg=None, **kw):
        bg = bg or Colors.surface
        super().__init__(master, bg=bg, highlightthickness=1,
                         highlightbackground=Colors.border,
                         highlightcolor=Colors.border, bd=0, **kw)
        self._pad = padding

    @property
    def content(self):
        """内部留白区域（把子控件放这里）。"""
        if not hasattr(self, "_inner"):
            self._inner = tk.Frame(self, bg=self.cget("bg"))
            self._inner.pack(fill="both", expand=True,
                             padx=self._pad, pady=self._pad)
        return self._inner


class Button(tk.Label):
    """按钮。三种外观：

    - ``primary``：实心主色，用于最重要的动作；
    - ``outline``：白底细边框，用于次要动作（一眼能看出是可点的）；
    - ``ghost``：无边框，仅悬停变色，用于最不显眼的位置。
    """

    def __init__(self, master, text, command=None, kind="primary",
                 fonts=None, padx=None, pady=None, **kw):
        self.fonts = fonts or Fonts()
        self.kind = kind
        palettes = {
            "primary": (Colors.primary, Colors.text_inverse, Colors.primary_hover, None),
            "outline": (Colors.surface, Colors.text, Colors.hover, Colors.border),
            "ghost": (Colors.surface, Colors.text, Colors.hover, None),
            "soft": (Colors.primary_soft, Colors.primary,
                     hex_blend(Colors.primary_soft, Colors.primary, 0.14), None),
        }
        self._bg, self._fg, self._hover, self._border = palettes.get(
            kind, palettes["primary"])
        super().__init__(master, text=text, bg=self._bg, fg=self._fg,
                         font=self.fonts.body("bold" if kind == "primary" else "normal"),
                         padx=padx if padx is not None else Space.lg,
                         pady=pady if pady is not None else Space.sm + 1,
                         cursor="hand2", bd=0,
                         highlightthickness=1 if self._border else 0,
                         highlightbackground=self._border or self._bg,
                         highlightcolor=self._border or self._bg, **kw)
        self._command = command
        self._enabled = True
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    def _on_enter(self, _e=None):
        if self._enabled:
            self.configure(bg=self._hover,
                           highlightbackground=self._border or self._hover)

    def _on_leave(self, _e=None):
        if self._enabled:
            self.configure(bg=self._bg,
                           highlightbackground=self._border or self._bg)

    def _on_click(self, _e=None):
        if self._enabled and self._command:
            self._command()

    def set_enabled(self, enabled):
        self._enabled = bool(enabled)
        if self._enabled:
            self.configure(bg=self._bg, fg=self._fg, cursor="hand2",
                           highlightbackground=self._border or self._bg)
        else:
            self.configure(bg=hex_blend(self._bg, Colors.bg, 0.55),
                           fg=Colors.text_faint, cursor="arrow",
                           highlightbackground=hex_blend(Colors.border, Colors.bg, 0.5))


class Link(tk.Label):
    """可点击的文字链接，悬停时变色。"""

    def __init__(self, master, text, url=None, command=None, fonts=None,
                 primary=False, anchor="w", **kw):
        self.fonts = fonts or Fonts()
        self._base_fg = Colors.primary if primary else Colors.primary
        self._hover_fg = Colors.primary_hover
        super().__init__(master, text=text, bg=kw.pop("bg", Colors.surface),
                         fg=self._base_fg, font=self.fonts.small(),
                         cursor="hand2", anchor=anchor, justify="left", **kw)
        self.url = url
        self._command = command
        self.bind("<Enter>", lambda e: self.configure(fg=self._hover_fg))
        self.bind("<Leave>", lambda e: self.configure(fg=self._base_fg))
        self.bind("<Button-1>", self._on_click)

    def _on_click(self, _e=None):
        if self._command:
            self._command()
        elif self.url:
            _open(self.url)


def _open(url):
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass


class DetailRow:
    """一行「标签 + 值 + 相关链接」，是详情区的基本单元。"""

    def __init__(self, master, label, fonts, bg=None):
        self.fonts = fonts
        self.bg = bg or Colors.surface
        self.frame = tk.Frame(master, bg=self.bg)
        self.frame.pack(fill="x", pady=(0, Space.md))
        self.label = tk.Label(self.frame, text=label, bg=self.bg,
                              fg=Colors.text_muted, font=self.fonts.small(),
                              anchor="nw", width=13)
        self.label.pack(side="left", anchor="n")
        self.holder = tk.Frame(self.frame, bg=self.bg)
        self.holder.pack(side="left", fill="x", expand=True)
        self.value = tk.Label(self.holder, text="—", bg=self.bg, fg=Colors.text,
                              font=self.fonts.body(), anchor="w", justify="left")
        self.value.pack(anchor="w", fill="x")
        # 值区宽度跟着面板变，长 URL 才不会溢出卡片
        self.value.bind("<Configure>", self._on_configure)
        self.links = tk.Frame(self.holder, bg=self.bg)
        self.links.pack(anchor="w", fill="x")

    def _on_configure(self, event):
        self.value.configure(wraplength=max(160, event.width - 4))

    def set(self, text, color=None):
        self.value.configure(text=text, fg=color or Colors.text)

    def clear_links(self):
        for w in self.links.winfo_children():
            w.destroy()

    def add_link(self, text, url=None, command=None, primary=False):
        link = Link(self.links, text, url=url, command=command, fonts=self.fonts,
                    primary=primary, bg=self.bg)
        link.pack(anchor="w", pady=(2, 0))
        return link

    def reset(self):
        self.set("—")
        self.clear_links()


class SearchBox(tk.Frame):
    """带聚焦高亮与占位提示的输入框。"""

    def __init__(self, master, fonts, placeholder="", on_submit=None,
                 on_change=None, on_navigate=None, on_escape=None, **kw):
        self.fonts = fonts
        self.placeholder = placeholder
        self._showing_placeholder = False
        super().__init__(master, bg=Colors.border, bd=0, **kw)
        self.inner = tk.Frame(self, bg=Colors.surface)
        self.inner.pack(fill="both", expand=True, padx=1, pady=1)

        self.var = tk.StringVar()
        self.entry = tk.Entry(self.inner, textvariable=self.var, bd=0,
                              relief="flat", bg=Colors.surface, fg=Colors.text,
                              font=self.fonts.f(size=self.fonts.size_subtitle),
                              insertbackground=Colors.text,
                              highlightthickness=0)
        self.entry.pack(fill="both", expand=True, padx=Space.md,
                        pady=Space.sm + 2)

        self.entry.bind("<FocusIn>", self._on_focus_in)
        self.entry.bind("<FocusOut>", self._on_focus_out)
        if on_submit:
            self.entry.bind("<Return>", lambda e: on_submit())
        if on_change:
            self.var.trace_add("write", lambda *a: on_change())
        if on_navigate:
            self.entry.bind("<Down>", lambda e: on_navigate(1))
            self.entry.bind("<Up>", lambda e: on_navigate(-1))
        if on_escape:
            self.entry.bind("<Escape>", lambda e: on_escape())

        self._show_placeholder()

    # -- 占位提示 -----------------------------------------------------------
    def _show_placeholder(self):
        if not self.var.get():
            self._showing_placeholder = True
            self.entry.configure(fg=Colors.text_faint)
            self.var.set(self.placeholder)

    def _clear_placeholder(self):
        if self._showing_placeholder:
            self._showing_placeholder = False
            self.var.set("")
            self.entry.configure(fg=Colors.text)

    def _on_focus_in(self, _e=None):
        self.configure(bg=Colors.focus)
        self._clear_placeholder()

    def _on_focus_out(self, _e=None):
        self.configure(bg=Colors.border)
        self._show_placeholder()

    # -- 取值 ---------------------------------------------------------------
    def get(self):
        return "" if self._showing_placeholder else self.var.get().strip()

    def set(self, text):
        self._showing_placeholder = False
        self.entry.configure(fg=Colors.text)
        self.var.set(text)

    def focus(self):
        self.entry.focus_set()


class SuggestionList(tk.Listbox):
    """卡名候选列表。"""

    def __init__(self, master, fonts, on_pick):
        super().__init__(master, height=0, activestyle="none", bd=0,
                         highlightthickness=1, highlightbackground=Colors.border,
                         selectbackground=Colors.primary_soft,
                         selectforeground=Colors.text,
                         bg=Colors.surface, fg=Colors.text,
                         font=fonts.body(), exportselection=False)
        self.fonts = fonts
        self._on_pick = on_pick
        self.bind("<Double-Button-1>", lambda e: self.pick())
        self.bind("<Return>", lambda e: self.pick())

    def show(self, names, limit=8):
        if not names:
            self.hide()
            return
        self.delete(0, "end")
        for name in names[:limit]:
            self.insert("end", "  " + name)
        self.configure(height=min(limit, len(names)))
        self.selection_clear(0, "end")
        self.selection_set(0)

    def hide(self):
        self.delete(0, "end")
        self.configure(height=0)

    def move(self, step):
        size = self.size()
        if not size:
            return
        current = self.curselection()
        index = (current[0] if current else -1) + step
        index = max(0, min(size - 1, index))
        self.selection_clear(0, "end")
        self.selection_set(index)
        self.see(index)

    def pick(self):
        sel = self.curselection()
        if not sel:
            return
        name = self.get(sel[0]).strip()
        self.hide()
        self._on_pick(name)


class StatusBar(tk.Frame):
    """底部状态栏：圆点 + 文字 + 右侧进度条。"""

    def __init__(self, master, fonts):
        super().__init__(master, bg=Colors.bg)
        self.fonts = fonts
        self.dot = tk.Label(self, text="●", bg=Colors.bg, fg=Colors.text_faint,
                            font=fonts.small())
        self.dot.pack(side="left", padx=(0, Space.xs + 2))
        self.label = tk.Label(self, text="", bg=Colors.bg, fg=Colors.text_muted,
                              font=fonts.small(), anchor="w")
        self.label.pack(side="left")
        from tkinter import ttk
        self.bar = ttk.Progressbar(self, mode="indeterminate", length=120)
        self.bar.pack(side="right")

    def set(self, text, kind="idle", busy=False):
        colors = {"idle": Colors.text_faint, "info": Colors.primary,
                  "success": Colors.success, "error": Colors.danger,
                  "warning": Colors.warning}
        self.dot.configure(fg=colors.get(kind, Colors.text_faint))
        self.label.configure(text=text,
                             fg=Colors.text if kind != "idle" else Colors.text_muted)
        if busy:
            self.bar.start(12)      # 重复调用是幂等的，定时器不会叠加
        else:
            self.bar.stop()


__all__ = ["Card", "Button", "Link", "DetailRow", "SearchBox", "SuggestionList",
           "StatusBar", "hex_blend"]
