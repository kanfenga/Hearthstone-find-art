# -*- coding: utf-8 -*-
"""主窗口。

职责：把 core 的查询结果画到界面上，并处理交互（搜索、建议、复制、缓存）。
界面细节都委托给 ui.widgets / ui.preview，这里只做编排。
"""
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from .. import config
from ..meta import APP_TITLE, DESCRIPTION, VERSION
from ..core import ApiError, Finder, NameIndex
from ..core.http import http_get
from .preview import PreviewPanel
from .theme import Colors, Fonts, Radius, Space, enable_dpi_awareness
from .widgets import Button, Card, DetailRow, Link, SearchBox, StatusBar, \
    SuggestionList, hex_blend

# 详情区字段顺序（后续加字段在这里追加即可）
FIELDS = [
    ("card_id", "卡牌 ID"),
    ("type_rarity", "类型 / 稀有度"),
    ("artist", "普通版画师"),
    ("signature_artist", "异画画师"),
    ("regular", "普通版全幅"),
    ("signature", "异画全幅"),
    ("source", "画师原始发布"),
    ("others", "同名衍生卡"),
]

TYPE_NAMES = {
    "MINION": "随从", "SPELL": "法术", "WEAPON": "武器", "LOCATION": "地标",
    "HERO": "英雄", "HERO_POWER": "英雄技能", "ENCHANTMENT": "附魔",
    "BATTLEGROUND_SPELL": "酒馆法术", "BATTLEGROUND_TRINKET": "酒馆饰品",
}
RARITY_NAMES = {
    "FREE": "免费", "COMMON": "普通", "RARE": "稀有", "EPIC": "史诗",
    "LEGENDARY": "传说",
}


class App:
    def __init__(self, root, index=None, finder=None):
        self.root = root
        self.queue = queue.Queue()
        self.index = index or NameIndex()
        self.finder = finder or Finder(self.index)
        self.result = None
        self.busy = False
        self.rows = {}

        self.fonts = Fonts()
        self._build_window()
        self._build_style()
        self._build_layout()
        self._bind_keys()
        self._pump()

        if self.index.ready:
            self.status.set(f"索引已就绪：{self.index.locale}，"
                            f"{self.index.count:,} 个卡名", "info")
        else:
            self.status.set(self.index.error or "卡名索引缺失，可用卡牌 ID 或英文名查询",
                            "warning")
        self.search.focus()

    # -- 窗口 ---------------------------------------------------------------
    def _build_window(self):
        self.root.title(f"{APP_TITLE} {VERSION}")
        self.root.configure(bg=Colors.bg)
        # 适配小屏：1366x768 也能放下
        w = min(1180, int(self.root.winfo_screenwidth() * 0.86))
        h = min(760, int(self.root.winfo_screenheight() * 0.86))
        self.root.geometry(f"{max(900, w)}x{max(620, h)}")
        self.root.minsize(880, 600)
        icon = self._icon_path()
        if icon:
            try:
                self.root.iconbitmap(default=icon)
            except Exception:
                pass

    @staticmethod
    def _icon_path():
        from ..core.paths import resource_path
        for name in ("icon.ico", "icon.png"):
            path = resource_path(name)
            if path and os.path.exists(path):
                return path
        return None

    def _build_style(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure(".", font=self.fonts.body(), background=Colors.bg,
                     foreground=Colors.text)
        st.configure("TFrame", background=Colors.bg)
        st.configure("TProgressbar", background=Colors.primary,
                     troughcolor=hex_blend(Colors.border, Colors.bg, 0.4),
                     bordercolor=Colors.bg, lightcolor=Colors.primary,
                     darkcolor=Colors.primary)

    # -- 布局 ---------------------------------------------------------------
    def _build_layout(self):
        outer = tk.Frame(self.root, bg=Colors.bg)
        outer.pack(fill="both", expand=True, padx=Space.xl, pady=(Space.lg, Space.md))

        self._build_header(outer)
        self._build_search(outer)
        self._build_body(outer)
        self._build_status(outer)

    def _build_header(self, parent):
        head = tk.Frame(parent, bg=Colors.bg)
        head.pack(fill="x")
        left = tk.Frame(head, bg=Colors.bg)
        left.pack(side="left")
        tk.Label(left, text=APP_TITLE, bg=Colors.bg, fg=Colors.text,
                 font=self.fonts.title()).pack(anchor="w")
        tk.Label(left, text=DESCRIPTION, bg=Colors.bg, fg=Colors.text_muted,
                 font=self.fonts.small()).pack(anchor="w", pady=(2, 0))

        right = tk.Frame(head, bg=Colors.bg)
        right.pack(side="right", anchor="n")
        tk.Label(right, text=f"v{VERSION}", bg=Colors.bg, fg=Colors.text_faint,
                 font=self.fonts.caption()).pack(anchor="e")
        self.backend_lbl = tk.Label(right, text="", bg=Colors.bg,
                                    fg=Colors.text_faint, font=self.fonts.caption())
        self.backend_lbl.pack(anchor="e", pady=(2, 0))
        self._describe_backend()

    def _describe_backend(self):
        """在标题栏角落标出预览用的解码后端，方便排查「预览不显示」。"""
        from ..core.images import GdiPlus, has_pillow
        if has_pillow():
            note = "预览：Pillow"
        elif GdiPlus.get() is not None and GdiPlus.get().available:
            note = "预览：系统 GDI+"
        else:
            note = "预览不可用"
        self.backend_lbl.configure(text=note)

    def _build_search(self, parent):
        wrap = tk.Frame(parent, bg=Colors.bg)
        wrap.pack(fill="x", pady=(Space.lg, Space.md))

        row = tk.Frame(wrap, bg=Colors.bg)
        row.pack(fill="x")
        self.search = SearchBox(
            row, self.fonts,
            placeholder="输入卡牌中文名，例如：时空大盗拉法姆",
            on_submit=self.on_search, on_change=self.on_type,
            on_navigate=self.on_navigate, on_escape=self.on_escape)
        self.search.pack(side="left", fill="x", expand=True, ipady=2)
        self.search_btn = Button(row, "查询", command=self.on_search,
                                 fonts=self.fonts)
        self.search_btn.pack(side="left", padx=(Space.sm, 0))

        self.suggest = SuggestionList(wrap, self.fonts, self.on_pick_suggest)

    def _build_body(self, parent):
        body = tk.Frame(parent, bg=Colors.bg)
        body.pack(fill="both", expand=True)
        # 预览随窗口变宽（权重略小，保证详情区更宽）
        body.columnconfigure(0, weight=2, minsize=340)
        body.columnconfigure(1, weight=3)
        body.rowconfigure(0, weight=1)

        self.preview = PreviewPanel(body, self.fonts, fetch=self._fetch_preview)
        self.preview.grid(row=0, column=0, sticky="nsew", padx=(0, Space.md))

        self.detail_card = Card(body, padding=Space.lg)
        self.detail_card.grid(row=0, column=1, sticky="nsew")
        content = self.detail_card.content

        # 卡名与副标题
        self.name_lbl = tk.Label(content, text="等待查询", bg=Colors.surface,
                                 fg=Colors.text, font=self.fonts.hero(),
                                 anchor="w")
        self.name_lbl.pack(anchor="w", fill="x")
        self.sub_lbl = tk.Label(content, text="输入卡牌中文名后回车",
                                bg=Colors.surface, fg=Colors.text_muted,
                                font=self.fonts.small(), anchor="w",
                                justify="left")
        self.sub_lbl.pack(anchor="w", fill="x", pady=(Space.xs, Space.md))

        separator = tk.Frame(content, bg=Colors.border, height=1)
        separator.pack(fill="x", pady=(0, Space.md))

        self.rows_holder = tk.Frame(content, bg=Colors.surface)
        self.rows_holder.pack(fill="both", expand=True)
        for key, label in FIELDS:
            self.rows[key] = DetailRow(self.rows_holder, label, self.fonts)

        # 底部按钮
        actions = tk.Frame(content, bg=Colors.surface)
        actions.pack(fill="x", pady=(Space.sm, 0))
        self.btn_wiki = Button(actions, "打开 wiki 页面", command=self.on_open_wiki,
                               kind="outline", fonts=self.fonts)
        self.btn_wiki.pack(side="left")
        self.btn_copy = Button(actions, "复制全部结果", command=self.on_copy,
                               kind="outline", fonts=self.fonts)
        self.btn_copy.pack(side="left", padx=(Space.sm, 0))
        self.btn_clear = Button(actions, "清空缓存", command=self.on_clear_cache,
                                kind="ghost", fonts=self.fonts, padx=Space.md)
        self.btn_clear.pack(side="right")
        self._set_actions(False)

    def _build_status(self, parent):
        bar = tk.Frame(parent, bg=Colors.bg)
        bar.pack(fill="x", pady=(Space.md, 0))
        self.status = StatusBar(bar, self.fonts)
        self.status.pack(fill="x")

    def _bind_keys(self):
        self.root.bind("<Control-l>", lambda e: self.search.focus())
        self.root.bind("<Control-f>", lambda e: self.search.focus())
        self.root.bind("<Control-c>", self._on_ctrl_c)
        self.root.bind("<F5>", lambda e: self.on_search())

    # -- 交互 ---------------------------------------------------------------
    def _set_actions(self, enabled):
        for btn in (self.btn_wiki, self.btn_copy):
            btn.set_enabled(enabled)

    def _set_busy(self, busy, text=None, kind="info"):
        self.busy = busy
        if text is not None:
            self.status.set(text, kind, busy=busy)
        elif not busy:
            self.status.set(self.status.label.cget("text"), kind, busy=False)
        self.search_btn.set_enabled(not busy)

    def on_type(self):
        text = self.search.get()
        if not text:
            self.suggest.hide()
            return
        self.suggest.show(self.index.similar(text))

    def on_navigate(self, step):
        if self.suggest.size():
            self.suggest.move(step)
        return "break"

    def on_escape(self):
        self.suggest.hide()
        self.search.set("")

    def on_pick_suggest(self, name):
        self.search.set(name)
        self.on_search()

    def on_search(self):
        if self.busy:
            return
        text = self.search.get()
        self.suggest.hide()
        if not text:
            self.search.focus()
            self.status.set("请输入卡牌中文名", "warning")
            return
        info, _ = self.index.lookup(text)
        if info is None and text not in self.index.cards:
            sim = self.index.similar(text)
            if sim and text not in sim:
                sim = [text] + sim
            if sim:
                self._render({"query": text, "error": f"卡名索引里没有「{text}」",
                              "candidates": sim[:20]})
                return
        self._set_busy(True, f"正在查询「{text}」…")
        threading.Thread(target=self._worker, args=(text,), daemon=True).start()

    def _worker(self, text):
        try:
            res = self.finder.find(text, log=lambda m: self.queue.put(("status", m)))
        except ApiError as e:
            # 网络类失败单独标出来：它不是「这张卡不存在」，
            # 界面要用不同措辞与配色，避免误导用户
            res = {"query": text, "error": str(e), "api_error": True}
        except Exception as e:
            res = {"query": text, "error": f"出错了：{type(e).__name__}: {e}"}
        self.queue.put(("result", res))

    def _pump(self):
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "status":
                    self._set_busy(True, payload)
                elif kind == "result":
                    self._render(payload)
                    if payload.get("error"):
                        kind_ = "warning" if payload.get("api_error") else "error"
                        self._set_busy(False, payload["error"], kind_)
                    else:
                        self._set_busy(False, "完成", "success")
                elif kind == "preview":
                    ticket, data = payload
                    self.preview.set_image(ticket, data)
        except queue.Empty:
            pass
        self.root.after(80, self._pump)

    # -- 预览取图 -----------------------------------------------------------
    def _fetch_preview(self, url, ticket):
        threading.Thread(target=self._preview_worker, args=(url, ticket),
                         daemon=True).start()

    def _preview_worker(self, url, ticket):
        try:
            data = self._download_preview(url)
            self.queue.put(("preview", (ticket, data)))
        except Exception:
            self.queue.put(("preview", (ticket, None)))

    @staticmethod
    def _download_preview(url):
        """下载缩略图；缩略图不存在时退回原图。

        缩略图 URL 必须用下划线形式：wiki 对带空格的「700px-文件名」返回 400。
        """
        base = url.split("?")[0]
        name = base.rsplit("/", 1)[-1]
        host = url.split("/images/")[0]
        width = config.PREVIEW_THUMB_WIDTH
        thumb = f"{host}/images/thumb/{name}/{width}px-{name}"
        try:
            return http_get(thumb, timeout=config.PREVIEW_TIMEOUT)
        except Exception:
            return http_get(url, timeout=config.PREVIEW_TIMEOUT * 2)

    # -- 渲染 ---------------------------------------------------------------
    def _render(self, res):
        for row in self.rows.values():
            row.reset()
        self.result = res
        self.preview.clear()

        if res.get("error"):
            api_error = bool(res.get("api_error"))
            # 网络/限流问题不能说成「没查到」——那会让人以为这张卡不存在
            self.name_lbl.configure(text="连接失败" if api_error else "没查到",
                                    fg=Colors.warning if api_error else Colors.danger)
            self.sub_lbl.configure(text=res["error"], fg=Colors.text_muted)
            self._set_actions(False)
            if not api_error:
                cands = res.get("candidates") or []
                if cands:
                    row = self.rows["card_id"]
                    row.set("可能想找的是（点一下再查）：", Colors.text_muted)
                    for name in cands:
                        row.add_link("· " + name,
                                     command=lambda n=name: self._pick_name(n))
            return

        self.name_lbl.configure(text=self._display_name(res), fg=Colors.text)
        self.sub_lbl.configure(text=self._subtitle(res), fg=Colors.text_muted)
        self._set_actions(True)

        self.rows["card_id"].set(res.get("card_id") or "—")
        self.rows["type_rarity"].set(res.get("type_rarity") or "—")
        self.rows["artist"].set(res.get("artist") or "（无记录）")
        self.rows["signature_artist"].set(
            res.get("signature_artist") or "（该卡无签名档）")

        sources = []
        for tag, key in (("regular", "regular"), ("signature", "signature")):
            info = (res.get("images") or {}).get(tag)
            row = self.rows[key]
            if not info or not info.get("url"):
                row.set("wiki 未收录全幅原稿", Colors.text_muted)
                continue
            row.set(f'{info["width"]}×{info["height"]}    {info.get("file") or ""}')
            row.add_link("▸ 打开高清原画", url=info["url"], primary=True)
            # 来源链接统一放到下面「画师原始发布」一行展示，这里不重复
            sources.extend(info.get("sources") or [])

        seen = list(dict.fromkeys(sources))
        row = self.rows["source"]
        if seen:
            row.set("\n".join(seen))
            for src in seen:
                row.add_link("▸ 在浏览器打开", url=src, primary=True)
        else:
            row.set("wiki 未标注来源（画师可能受 NDA 约束未发布）", Colors.text_muted)

        others = res.get("others") or []
        if others:
            self.rows["others"].set(
                "、".join(f"{i}({t.lower()})" for i, t in others)
                + "  —— 同名但无独立原画")
        else:
            self.rows["others"].set("无", Colors.text_faint)

        self.preview.show(res.get("images") or {})

    def _display_name(self, res):
        return res.get("name_zh") or res.get("name") or res.get("page") or "?"

    def _subtitle(self, res):
        bits = [b for b in (res.get("card_id"), f'dbfId={res.get("dbfId")}',
                            res.get("page")) if b]
        return "   ·   ".join(bits)

    def _pick_name(self, name):
        self.search.set(name)
        self.on_search()

    # -- 按钮 ---------------------------------------------------------------
    def on_open_wiki(self):
        if self.result and self.result.get("wiki"):
            from .widgets import _open
            _open(self.result["wiki"])

    def on_copy(self):
        if not self.result or self.result.get("error"):
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.result_as_text())
        self.status.set("已复制到剪贴板", "success")

    def result_as_text(self):
        """把结果整理成纯文本（复制用，也方便将来导出）。"""
        r = self.result or {}
        lines = [f'{self._display_name(r)}   [{r.get("card_id") or "-"}  '
                 f'dbfId={r.get("dbfId")}]',
                 f'wiki: {r.get("wiki")}']
        if r.get("type_rarity"):
            lines.append(f'类型/稀有度: {r["type_rarity"]}')
        lines.append(f'普通版画师: {r.get("artist") or "（无）"}')
        lines.append(f'异画画师: {r.get("signature_artist") or "（该卡无签名档）"}')
        for tag, label in (("regular", "普通版全幅"), ("signature", "异画全幅")):
            info = (r.get("images") or {}).get(tag)
            if not info or not info.get("url"):
                lines.append(f"{label}: 无（wiki 未收录）")
                continue
            lines.append(f'{label}: {info["width"]}×{info["height"]}  {info["url"]}')
            for src in info.get("sources") or []:
                lines.append(f"    画师原始发布: {src}")
        return "\n".join(lines)

    def _on_ctrl_c(self, _event=None):
        # 只在输入框没聚焦时接管，避免影响正常的文本复制
        if self.root.focus_get() is not self.search.entry:
            self.on_copy()

    def on_clear_cache(self):
        if not messagebox.askyesno("清空缓存",
                                   "清空已缓存的查询结果？\n"
                                   "（下次查询会重新联网，稍慢但结果最新）"):
            return
        self.finder.clear_cache()
        self.status.set("缓存已清空", "success")


def run(cli_args=None):
    """入口：创建窗口并进入事件循环。``cli_args`` 里的第一个词当作预填卡名。"""
    enable_dpi_awareness()
    root = tk.Tk()
    app = App(root)
    name = " ".join(cli_args or []).strip()
    if name:
        app.search.set(name)
        root.after(150, app.on_search)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    return 0


__all__ = ["App", "run"]
