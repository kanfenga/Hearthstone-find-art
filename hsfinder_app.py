#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hsfinder —— 炉石原画查询器（图形界面）。

输入卡牌中文名（或卡牌 ID / dbfId / 英文页面名），一次给出：
  · 普通版 / 金卡版画师
  · 异画（Signature）画师 —— 官方 API 查不到，这是本工具的核心
  · 普通版与异画的高清全幅直链与像素尺寸
  · 画师本人的原始发布页（Instagram / X / ArtStation / 个人站）

依赖：仅 Python 标准库 + tkinter。发布版已内嵌卡名索引，中文名查询零下载。
"""
import json
import os
import queue
import re
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox

APP_NAME = "hsfinder"
APP_TITLE = "炉石原画查询器"
VERSION = "1.0"

API = "https://hearthstone.wiki.gg/api.php"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
URL_RE = re.compile(r"https?://[^\s\]\}<>\"|]+")
TIMEOUT = 20
RETRIES = 2
# wiki 会限流：脚本连续快速请求会收到 HTTP 429。两次请求之间至少隔这么久，
# 并在这把锁上串行化，避免多线程同时打。
MIN_INTERVAL = 0.25
_rate_lock = threading.Lock()
_last_call = [0.0]


def _throttle():
    with _rate_lock:
        gap = time.monotonic() - _last_call[0]
        if gap < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - gap)
        _last_call[0] = time.monotonic()

PLACEHOLDER = "输入卡牌中文名，例如：时空大盗拉法姆"


# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(name):
    """打包后从 exe 解出的临时目录取，开发时从脚本目录取。"""
    base = getattr(sys, "_MEIPASS", None) or app_dir()
    return os.path.join(base, name)


def cache_dir():
    """查询缓存目录。可用环境变量 HSFINDER_CACHE 覆盖（便携用法：指到 U 盘）。"""
    override = os.environ.get("HSFINDER_CACHE")
    if override:
        d = override
    else:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        d = os.path.join(base, APP_NAME)
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        # 目录不可写时退回 exe/脚本所在目录，保证程序仍能跑
        d = os.path.join(app_dir(), "cache")
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass
    return d


# ---------------------------------------------------------------------------
# 网络层
# ---------------------------------------------------------------------------
class ApiError(Exception):
    """wiki API 请求失败（网络不可达 / HTTP 错误 / 返回不可解析）。"""


def http_get(url, timeout=TIMEOUT, headers=None):
    h = {"User-Agent": UA, "Referer": "https://hearthstone.wiki.gg/"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def api(**params):
    """MediaWiki API。带限流与退避重试；网络失败抛 ApiError，与「查不到」区分开。"""
    qs = urllib.parse.urlencode(params)
    url = f"{API}?{qs}"
    deadline = time.monotonic() + TIMEOUT * (RETRIES + 1) + 12
    last = None
    for attempt in range(RETRIES + 1):
        if time.monotonic() > deadline:
            break
        _throttle()
        try:
            raw = http_get(url, timeout=TIMEOUT).decode("utf-8", "replace")
            return json.loads(raw)
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code} {e.reason}"
            if e.code == 429:
                # 被限流：等一会儿再试，等的时间逐次加长
                time.sleep(1.5 + 2.5 * attempt)
                continue
            if e.code in (403, 404):
                break
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
        time.sleep(0.8 + attempt)
    if last and "429" in last:
        raise ApiError("查询太频繁，被 wiki 限流了，请等几秒再试")
    raise ApiError(f"连不上 wiki（{last}）")


def cargo(where):
    d = api(action="cargoquery", tables="DerivedCard",
            fields="_pageName,artist,signatureArtist,dbfId",
            where=where, limit=1, format="json")
    rows = d.get("cargoquery") or []
    return rows[0]["title"] if rows else None


def imageinfo(filename):
    d = api(action="query", titles=f"File:{filename}", prop="imageinfo",
            iiprop="url|size|mime", format="json", formatversion=2)
    pages = (d.get("query") or {}).get("pages") or []
    if not pages:
        return None
    ii = (pages[0].get("imageinfo") or [None])[0]
    # wiki 对不存在的 File 有时会返回全 null 的条目，这里统一归一成 None
    if not ii or not ii.get("url"):
        return None
    return ii


def wiki_search(text, limit=8):
    """全文搜索，用于索引里没有的名字（英文名、外号、写错的中文名）。"""
    d = api(action="query", list="search", srsearch=text, srlimit=limit, format="json")
    return [(r.get("title"), r.get("size")) for r in (d.get("query") or {}).get("search") or []]


def page_files(page, kind):
    """从卡片页的图片列表里找全幅原稿的真实文件名。

    文件名不总是「页面名 + _full.jpg」：例如 Power Word: Glory 的实际文件是
    Power_Word-_Glory_full.jpg（冒号被换成横线），靠拼接猜不到，只能去页面里找。
    kind: "full" 或 "signature_full"。
    """
    d = api(action="query", titles=page, prop="images", imlimit=200,
            format="json", formatversion=2)
    pages = (d.get("query") or {}).get("pages") or []
    want = f"_{kind}.jpg"
    hits = []
    for p in pages:
        for im in p.get("images") or []:
            title = (im.get("title") or "").replace("File:", "")
            if title.endswith(want) or title.lower().endswith(want):
                hits.append(title)
    if not hits:
        return None
    # 优先不含 "(golden)" 之类后缀的规范名
    hits.sort(key=lambda s: (len(s), s))
    return hits[0]


def source_of(filename):
    """File 描述页 wikitext 里的 source 字段 = 画师本人的发布链接。"""
    d = api(action="parse", page=f"File:{filename}", prop="wikitext",
            format="json", formatversion=2)
    return URL_RE.findall(((d.get("parse") or {}).get("wikitext") or ""))


# ---------------------------------------------------------------------------
# 卡名索引
# ---------------------------------------------------------------------------
class NameIndex:
    """中文名 / 卡牌ID / dbfId -> 卡牌信息。优先用内嵌索引，其次用户数据目录。"""

    def __init__(self):
        self.cards = {}
        self.by_id = {}
        self.by_dbf = {}
        self.locale = "?"
        self.source = "（无）"
        self._load()

    def _load(self):
        for path in (resource_path("names.json"),
                     os.path.join(cache_dir(), "names.json")):
            if not os.path.exists(path):
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    d = json.load(f)
                self.cards = d.get("cards") or {}
                self.locale = d.get("locale", "?")
                self.source = path
                break
            except Exception:
                continue
        # 反查表只建一次，避免每次查询遍历两万多个卡名
        for name, v in self.cards.items():
            if v.get("id"):
                self.by_id.setdefault(v["id"], name)
            if v.get("dbfId") is not None:
                self.by_dbf.setdefault(str(v["dbfId"]), name)

    def name_of(self, entry):
        """由条目反查规范中文名（O(1)）。"""
        if not entry:
            return None
        if entry.get("id") and entry["id"] in self.by_id:
            return self.by_id[entry["id"]]
        if entry.get("dbfId") is not None:
            return self.by_dbf.get(str(entry["dbfId"]))
        return None

    def lookup(self, text):
        """返回 (卡牌信息, 候选列表)。text 可以是中文名 / 卡牌ID / dbfId。"""
        t = (text or "").strip()
        if not t:
            return None, []
        hit = self.cards.get(t)
        if hit:
            return hit, []
        # 卡牌 ID 或 dbfId 反查
        name = self.by_id.get(t) or self.by_dbf.get(t)
        if name:
            return self.cards[name], []
        # 找不到精确的，给个包含匹配的候选
        cands = self.similar(t)
        return None, cands

    def similar(self, text, limit=20):
        t = (text or "").strip()
        if not t:
            return []
        out = [n for n in self.cards if t in n and n != t]
        out.sort(key=lambda n: (len(n), n))
        if t in self.cards:
            out.insert(0, t)
        return out[:limit]


# ---------------------------------------------------------------------------
# 查询与结果缓存
# ---------------------------------------------------------------------------
class Finder:
    def __init__(self, index):
        self.index = index
        self.cache_path = os.path.join(cache_dir(), "cache.json")
        self.cache = {}
        try:
            if os.path.exists(self.cache_path):
                with open(self.cache_path, encoding="utf-8") as f:
                    self.cache = json.load(f)
        except Exception:
            self.cache = {}

    def save_cache(self):
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False)
        except Exception:
            pass

    def find(self, text, use_cache=True, log=None):
        """查一张卡。返回结果 dict；失败时带 error / api_error 字段。"""
        say = log or (lambda *_: None)
        t = (text or "").strip()
        if not t:
            return {"error": "请输入卡牌中文名"}

        key = t.lower()
        if use_cache and key in self.cache:
            say("命中本地缓存")
            return self.cache[key]

        info, cands = self.index.lookup(t)
        where = None
        if info and info.get("dbfId"):
            where = f'dbfId="{info["dbfId"]}"'
        elif t.isdigit():
            where = f'dbfId="{t}"'
        else:
            where = f'_pageName="{t.replace("_", " ")}"'

        say("查询 wiki 画师数据…")
        row = cargo(where)
        if not row and "_" in t:
            row = cargo(f'_pageName="{t.replace("_", " ")}"')
        if not row and not info:
            # 索引里没有：先让 wiki 搜索一次，再拿搜到的页面名去查
            # （覆盖英文名、外号、以及记错的中文名）
            say("索引里没有，改用 wiki 搜索…")
            hits = wiki_search(t)
            for title, _size in hits[:4]:
                row = cargo(f'_pageName="{title}"')
                if row:
                    break
            if not row and hits:
                res = {
                    "query": t,
                    "error": f"wiki 上有这些相关页面，但没有对应的卡牌数据",
                    "candidates": [h[0] for h in hits[:8]],
                }
                return res
        if not row:
            msg = f"没有找到「{t}」这张卡"
            if info:
                msg = f"找不到「{t}」对应的 wiki 页面（该卡可能未被 wiki 收录）"
            return {"query": t, "error": msg, "candidates": cands}

        page = row["_pageName"]
        base = page.replace(" ", "_")
        # Cargo 里签名画师字段为空字符串 = wiki 未记录该卡有异画
        sig_artist = (row.get("signatureArtist") or "").strip() or None
        try:
            dbf = int(row.get("dbfId"))
        except (TypeError, ValueError):
            dbf = row.get("dbfId")
        # 页面名可能是 "Fireball (Core)" 这类消歧义名，而图片文件名不带括号
        base_alt = re.sub(r"\s*\([^)]*\)", "", page).replace(" ", "_")
        result = {
            "query": t,
            "name": (info or {}).get("name") or None,
            "name_zh": self.index.name_of(info),
            "card_id": (info or {}).get("id"),
            "dbfId": dbf,
            "page": page,
            "wiki": f"https://hearthstone.wiki.gg/wiki/{urllib.parse.quote(base)}",
            "artist": row.get("artist") or None,
            "signature_artist": sig_artist,
            "others": (info or {}).get("others") or [],
            "images": {},
        }

        def file_info(names):
            """按候选文件名依次试，返回 (文件名, imageinfo)。"""
            for nm in names:
                if not nm:
                    continue
                ii = imageinfo(nm)
                if ii:
                    return nm, ii
            return None, None

        for tag, key in (("regular", "full"), ("signature", "signature_full")):
            say(f"查询{'异画' if tag == 'signature' else '普通版'}全幅原画…")
            # 先按页面名猜（命中率最高），猜不到再去卡片页的图片列表里找真实文件名
            fn, ii = file_info([f"{base}_{key}.jpg",
                                f"{base_alt}_{key}.jpg" if base_alt != base else None])
            if not ii:
                try:
                    real = page_files(page, key)
                except ApiError:
                    real = None
                if real:
                    fn, ii = real, imageinfo(real)
            if not ii:
                result["images"][tag] = None
                continue
            try:
                src = source_of(fn)
            except ApiError:
                src = []
            result["images"][tag] = {
                "file": fn,
                "width": ii.get("width"),
                "height": ii.get("height"),
                "url": ii.get("url"),
                "sources": src,
            }
        if use_cache:
            self.cache[key] = result
            self.save_cache()
        return result


# ---------------------------------------------------------------------------
# 界面
# ---------------------------------------------------------------------------
FONT = ("Microsoft YaHei UI", 10)
FONT_SMALL = ("Microsoft YaHei UI", 9)
FONT_TITLE = ("Microsoft YaHei UI", 13, "bold")
FONT_H = ("Microsoft YaHei UI", 11, "bold")


def open_url(url):
    try:
        webbrowser.open(url)
    except Exception:
        pass


class App:
    def __init__(self, root):
        self.root = root
        self.index = NameIndex()
        self.finder = Finder(self.index)
        self.queue = queue.Queue()
        self.busy = False
        self.result = None
        self.preview_img = None
        self._preview_ticket = 0

        root.title(f"{APP_TITLE} {VERSION}")
        root.geometry("1080x740")
        root.minsize(900, 620)
        try:
            root.iconbitmap(default=resource_path("icon.ico"))
        except Exception:
            pass

        self._build_style()
        self._build_ui()
        self._set_status(f"索引已就绪：{self.index.locale}，"
                         f"{len(self.index.cards):,} 个卡名")
        root.after(80, self._pump)
        self.entry.focus_set()

    # -- 视觉 -----------------------------------------------------------------
    def _build_style(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except Exception:
            pass
        bg, panel, accent = "#f4f5f7", "#ffffff", "#1f6feb"
        self.root.configure(bg=bg)
        st.configure(".", font=FONT, background=bg, foreground="#1c1e21")
        st.configure("TFrame", background=bg)
        st.configure("Card.TFrame", background=panel, relief="flat")
        st.configure("TLabel", background=bg)
        st.configure("Card.TLabel", background=panel)
        st.configure("Title.TLabel", font=FONT_TITLE, background=bg)
        st.configure("Hint.TLabel", font=FONT_SMALL, foreground="#6b7280", background=bg)
        st.configure("Field.TLabel", font=FONT_SMALL, foreground="#6b7280", background=panel)
        st.configure("Value.TLabel", font=("Microsoft YaHei UI", 11), background=panel)
        st.configure("Big.TLabel", font=FONT_H, background=panel)
        st.configure("TButton", padding=(14, 7))
        st.configure("Go.TButton", font=FONT_H, padding=(18, 7))
        self.accent = accent

    # -- 布局 -----------------------------------------------------------------
    def _build_ui(self):
        top = ttk.Frame(self.root, padding=(16, 14, 16, 8))
        top.pack(fill="x")
        ttk.Label(top, text=APP_TITLE, style="Title.TLabel").pack(side="left")
        ttk.Label(top, text="  输入中文名即可查到画师与最高清原画",
                  style="Hint.TLabel").pack(side="left", padx=(6, 0))

        bar = ttk.Frame(self.root, padding=(16, 0, 16, 6))
        bar.pack(fill="x")
        self.var = tk.StringVar()
        self.entry = ttk.Entry(bar, textvariable=self.var, font=("Microsoft YaHei UI", 13))
        self.entry.pack(side="left", fill="x", expand=True, ipady=6)
        self.entry.bind("<Return>", lambda e: self.on_search())
        self.entry.bind("<KeyRelease>", self.on_type)
        self.go = ttk.Button(bar, text="查询", style="Go.TButton", command=self.on_search)
        self.go.pack(side="left", padx=(8, 0))

        self.suggest = tk.Listbox(self.root, height=0, font=FONT,
                                  activestyle="none", highlightthickness=1,
                                  highlightbackground="#d7dae0", borderwidth=0)
        self.suggest.bind("<Double-Button-1>", self.on_pick_suggest)
        self.suggest.bind("<Return>", self.on_pick_suggest)
        self._suggest_anchor = bar   # 建议框插在搜索栏之后

        body = ttk.Frame(self.root, padding=(16, 4, 16, 6))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=0, minsize=360)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # 左：预览
        left = tk.Frame(body, bg="#ffffff", highlightthickness=1,
                        highlightbackground="#e3e5e8")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.preview = tk.Label(left, text="原画预览", bg="#ffffff", fg="#9aa0a6",
                                font=FONT_SMALL)
        self.preview.pack(fill="both", expand=True, padx=8, pady=8)
        self.preview_note = tk.Label(left, text="", bg="#ffffff", fg="#9aa0a6",
                                     font=("Microsoft YaHei UI", 8), wraplength=330)
        self.preview_note.pack(fill="x", padx=8, pady=(0, 8))

        # 右：详情
        right = tk.Frame(body, bg="#ffffff", highlightthickness=1,
                         highlightbackground="#e3e5e8")
        right.grid(row=0, column=1, sticky="nsew")

        head = tk.Frame(right, bg="#ffffff")
        head.pack(fill="x", padx=16, pady=(14, 4))
        self.name_lbl = tk.Label(head, text="等待查询", bg="#ffffff", fg="#1c1e21",
                                 font=("Microsoft YaHei UI", 16, "bold"), anchor="w")
        self.name_lbl.pack(anchor="w")
        self.sub_lbl = tk.Label(head, text="", bg="#ffffff", fg="#6b7280",
                                font=FONT_SMALL, anchor="w")
        self.sub_lbl.pack(anchor="w", pady=(2, 0))

        self.rows = tk.Frame(right, bg="#ffffff")
        self.rows.pack(fill="both", expand=True, padx=16, pady=(8, 6))
        self.rows.columnconfigure(0, weight=1)
        self._row_widgets = {}

        btns = tk.Frame(right, bg="#ffffff")
        btns.pack(fill="x", padx=16, pady=(0, 14))
        self.btn_wiki = ttk.Button(btns, text="打开 wiki 页面", command=self.on_open_wiki)
        self.btn_wiki.pack(side="left")
        self.btn_copy = ttk.Button(btns, text="复制全部结果", command=self.on_copy)
        self.btn_copy.pack(side="left", padx=6)
        self.btn_clear = ttk.Button(btns, text="清空缓存", command=self.on_clear_cache)
        self.btn_clear.pack(side="right")
        for b in (self.btn_wiki, self.btn_copy):
            b.state(["disabled"])

        # 底部状态栏
        status = ttk.Frame(self.root, padding=(16, 0, 16, 10))
        status.pack(fill="x")
        self.progress = ttk.Progressbar(status, mode="indeterminate", length=140)
        self.status = ttk.Label(status, text="", style="Hint.TLabel")
        self.status.pack(side="left")
        self.progress.pack(side="right")

        self._add_row("card_id", "卡牌 ID")
        self._add_row("artist", "普通/金卡画师")
        self._add_row("signature_artist", "异画画师")
        self._add_row("regular", "普通版全幅")
        self._add_row("signature", "异画全幅")
        self._add_row("source", "画师原始发布")
        self._add_row("others", "同名衍生卡")

    def _add_row(self, key, label):
        box = tk.Frame(self.rows, bg="#ffffff")
        box.pack(fill="x", pady=(0, 10))
        tk.Label(box, text=label, bg="#ffffff", fg="#6b7280", font=FONT_SMALL,
                 anchor="w", width=13).pack(side="left", anchor="n")
        holder = tk.Frame(box, bg="#ffffff")
        holder.pack(side="left", fill="x", expand=True)
        val = tk.Label(holder, text="—", bg="#ffffff", fg="#1c1e21",
                       font=("Microsoft YaHei UI", 11), anchor="w", justify="left",
                       wraplength=560)
        val.pack(anchor="w")
        links = tk.Frame(holder, bg="#ffffff")
        links.pack(anchor="w", fill="x")
        self._row_widgets[key] = (val, links)

    # -- 交互 -----------------------------------------------------------------
    def _set_status(self, text, busy=False):
        self.status.configure(text=text)
        if busy and not self.busy:
            self.progress.start(12)
        elif not busy and self.busy:
            self.progress.stop()
        self.busy = busy
        self.go.state(["disabled"] if busy else ["!disabled"])

    def on_type(self, _evt=None):
        """输入时给卡名建议。"""
        text = self.var.get().strip()
        if not text:
            self._hide_suggest()
            return
        names = self.index.similar(text)
        if not names:
            self._hide_suggest()
            return
        self.suggest.delete(0, "end")
        for n in names[:8]:
            self.suggest.insert("end", "  " + n)
        self.suggest.configure(height=min(8, len(names)))
        self.suggest.pack(fill="x", padx=16, pady=(0, 4), after=self._suggest_anchor)

    def _hide_suggest(self):
        self.suggest.pack_forget()

    def on_pick_suggest(self, _evt=None):
        sel = self.suggest.curselection()
        if sel:
            self.var.set(self.suggest.get(sel[0]).strip())
        self._hide_suggest()
        self.on_search()

    def on_search(self):
        if self.busy:
            return
        text = self.var.get().strip()
        self._hide_suggest()
        if not text:
            self._set_status("请输入卡牌中文名")
            self.entry.focus_set()
            return
        info, cands = self.index.lookup(text)
        if info is None and text not in self.index.cards:
            sim = self.index.similar(text)
            if sim and text not in sim:
                sim = [text] + sim
            self._render(
                {"query": text,
                 "error": f"卡名索引里没有「{text}」",
                 "candidates": sim[:20]},
                allow_retry=True)
            return
        self._set_status(f"正在查询「{text}」…", busy=True)
        threading.Thread(target=self._worker, args=(text,), daemon=True).start()

    def _worker(self, text):
        try:
            res = self.finder.find(text, log=lambda m: self.queue.put(("status", m)))
        except ApiError as e:
            res = {"query": text, "error": str(e), "api_error": True}
        except Exception as e:
            res = {"query": text, "error": f"出错了：{type(e).__name__}: {e}",
                   "trace": traceback.format_exc()}
        self.queue.put(("result", res))

    def _pump(self):
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "status":
                    self._set_status(payload, busy=True)
                elif kind == "result":
                    self._render(payload)
                    self._set_status("完成" if not payload.get("error") else "没查到")
                elif kind == "preview":
                    self._show_preview(payload)
        except queue.Empty:
            pass
        self.root.after(80, self._pump)

    # -- 渲染 -----------------------------------------------------------------
    def _clear_rows(self):
        for val, links in self._row_widgets.values():
            val.configure(text="—", fg="#1c1e21")
            for w in links.winfo_children():
                w.destroy()

    def _set_row(self, key, text, color="#1c1e21"):
        val, _ = self._row_widgets[key]
        val.configure(text=text, fg=color)

    def _add_link(self, key, label, url, primary=False):
        _, links = self._row_widgets[key]
        fg = self.accent if primary else "#1f6feb"
        btn = tk.Label(links, text=label, bg="#ffffff", fg=fg, font=FONT_SMALL,
                       cursor="hand2", anchor="w", justify="left")
        btn.pack(anchor="w")
        btn.bind("<Button-1>", lambda e, u=url: open_url(u))
        btn.bind("<Enter>", lambda e: btn.configure(fg="#0b4fc0"))
        btn.bind("<Leave>", lambda e: btn.configure(fg=fg))
        return btn

    def _render(self, res, allow_retry=False):
        self._clear_rows()
        self.preview.configure(image="", text="原画预览")
        self.preview_note.configure(text="")
        self.preview_img = None
        self.result = res

        if res.get("error"):
            self.name_lbl.configure(text="没查到", fg="#b42318")
            self.sub_lbl.configure(text=res["error"])
            cands = res.get("candidates") or []
            if cands:
                val, links = self._row_widgets["card_id"]
                val.configure(text="可能想找的是（点一下再查）：")
                for n in cands:
                    self._add_link("card_id", "· " + n, f"pick://{n}")
                for w in links.winfo_children():
                    w.bind("<Button-1>", lambda e, n=n: self._pick_name(n))
            self.btn_wiki.state(["disabled"])
            self.btn_copy.state(["disabled"])
            self._set_status(res["error"])
            return

        name = res.get("name_zh") or res.get("name") or res.get("page")
        self.name_lbl.configure(text=name, fg="#1c1e21")
        bits = []
        if res.get("card_id"):
            bits.append(res["card_id"])
        bits.append(f'dbfId={res.get("dbfId")}')
        bits.append(res.get("page") or "")
        self.sub_lbl.configure(text="   ·   ".join(b for b in bits if b))

        self._set_row("card_id", res.get("card_id") or "—")
        self._set_row("artist", res.get("artist") or "（无记录）")
        self._set_row("signature_artist",
                      res.get("signature_artist") or "（该卡无签名档）")

        for tag, key in (("regular", "regular"), ("signature", "signature")):
            im = (res.get("images") or {}).get(tag)
            if not im or not im.get("url"):
                self._set_row(key, "wiki 未收录全幅原稿", color="#6b7280")
                continue
            self._set_row(key, f'{im["width"]}×{im["height"]}   ' +
                          (im.get("file") or ""))
            self._add_link(key, "▸ 打开高清原画", im.get("url"), primary=True)
            for u in (im.get("sources") or []):
                self._add_link(key, "▸ " + u, u)

        srcs = []
        for tag in ("regular", "signature"):
            im = (res.get("images") or {}).get(tag)
            if im and im.get("url"):
                srcs += im.get("sources") or []
        self._set_row("source", "；".join(dict.fromkeys(srcs)) if srcs
                      else "wiki 未标注来源（画师可能受 NDA 约束未发布）")
        for u in dict.fromkeys(srcs):
            self._add_link("source", "▸ " + u, u, primary=True)

        if res.get("others"):
            txt = "、".join(f"{i}({t.lower()})" for i, t in res["others"])
            self._set_row("others", txt + "  —— 同名但无独立原画")

        self.btn_wiki.state(["!disabled"])
        self.btn_copy.state(["!disabled"])
        self._load_preview(res)

    def _pick_name(self, name):
        self.var.set(name)
        self.on_search()

    def _load_preview(self, res):
        im = (res.get("images") or {}).get("regular") or (res.get("images") or {}).get("signature")
        if not im or not im.get("url"):
            self.preview.configure(text="没有可预览的原画")
            return
        self._preview_ticket += 1
        ticket = self._preview_ticket
        self.preview_note.configure(text="正在载入预览图…")
        threading.Thread(target=self._preview_worker,
                         args=(ticket, im["url"], im.get("width"), im.get("height")),
                         daemon=True).start()

    def _preview_worker(self, ticket, url, w, h):
        try:
            # 走 wiki 的缩略图服务，避免拉十几 MB 的原图
            thumb = url
            if w and w > 700:
                name = url.rsplit("/", 1)[-1].split("?")[0]
                thumb = url.split("/images/")[0] + f"/images/thumb/{name}/700px-{name}"
            data = http_get(thumb, timeout=30)
            self.queue.put(("preview", (ticket, data, w, h)))
        except Exception:
            self.queue.put(("preview", (ticket, None, w, h)))

    def _show_preview(self, payload):
        ticket, data, w, h = payload
        if ticket != self._preview_ticket:
            return
        if not data:
            self.preview.configure(text="原画预览")
            self.preview_note.configure(text="预览图载入失败（可点右侧链接直接打开）")
            return
        try:
            import base64
            img = tk.PhotoImage(data=base64.b64encode(data))
            maxw, maxh = 330, 430
            step = 1
            while img.width() // step > maxw or img.height() // step > maxh:
                step += 1
            if step > 1:
                img = img.subsample(step, step)
            self.preview_img = img
            self.preview.configure(image=img, text="")
            self.preview_note.configure(text=f"预览（原图 {w}×{h}）")
        except Exception as e:
            self.preview.configure(text="原画预览")
            self.preview_note.configure(text=f"预览失败：{e}")

    # -- 按钮 -----------------------------------------------------------------
    def on_open_wiki(self):
        if self.result and self.result.get("wiki"):
            open_url(self.result["wiki"])

    def on_copy(self):
        if not self.result or self.result.get("error"):
            return
        r = self.result
        lines = [f'{r.get("name_zh") or r.get("name") or r.get("page")}   '
                 f'[{r.get("card_id") or "-"}  dbfId={r.get("dbfId")}]',
                 f'wiki: {r.get("wiki")}',
                 f'普通/金卡画师: {r.get("artist") or "（无）"}',
                 f'异画画师: {r.get("signature_artist") or "（该卡无签名档）"}']
        for tag, label in (("regular", "普通版全幅"), ("signature", "异画全幅")):
            im = (r.get("images") or {}).get(tag)
            if not im or not im.get("url"):
                lines.append(f"{label}: 无（wiki 未收录全幅原稿）")
                continue
            lines.append(f'{label}: {im["width"]}×{im["height"]}  {im["url"]}')
            for u in im.get("sources") or []:
                lines.append(f"    画师原始发布: {u}")
        text = "\n".join(lines)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._set_status("已复制到剪贴板")

    def on_clear_cache(self):
        if not messagebox.askyesno("清空缓存", "清空已缓存的查询结果？\n"
                                              "（下次查询会重新联网，较慢但结果最新）"):
            return
        self.finder.cache = {}
        self.finder.save_cache()
        self._set_status("缓存已清空")


def _repair_argv():
    """修复命令行中文参数乱码，并丢掉可能的脚本名参数。

    pythonw.exe（无控制台）下 CPython 会按系统 ANSI 代码页解命令行，
    中文卡名会变成「鏃剁┖澶х洍鎷夋硶濮?」这类乱码；从资源管理器双击 .py
    时还会把脚本路径塞进 argv。这里统一收拾干净。
    """
    out = []
    for i, a in enumerate(sys.argv):
        if i == 0:
            continue
        # 双击运行 .py 时 argv[1] 是脚本自身路径
        if i == 1 and not out and a.lower().endswith((".py", ".pyw", ".exe")):
            base = os.path.basename(a).lower()
            if base == os.path.basename(sys.argv[0]).lower() or "hsfinder" in base:
                continue
        # 乱码修复：正确的中文被按 ANSI 代码页解读过，所以按 ANSI 编码回去、
        # 再按 UTF-8 解出来即可还原。仅当还原成功且结果确实变化时才采用。
        if any(ord(ch) > 127 for ch in a):
            for enc in ("cp936", "mbcs", "cp1252"):
                try:
                    fixed = a.encode(enc).decode("utf-8")
                except Exception:
                    continue
                if fixed != a and any(ord(ch) > 127 for ch in fixed):
                    a = fixed
                    break
        out.append(a)
    return out


CLI_ARGS = _repair_argv()

# 排查用：设了 HSFINDER_ARGLOG 就把实际收到的命令行参数写出去
_arglog = os.environ.get("HSFINDER_ARGLOG")
if _arglog:
    try:
        with open(_arglog, "w", encoding="utf-8") as _f:
            _f.write(repr(CLI_ARGS))
    except Exception:
        pass


def main():
    root = tk.Tk()
    app = App(root)
    # 支持命令行直接带卡名启动：hsfinder 时空大盗拉法姆
    name = " ".join(CLI_ARGS).strip()
    if name and name not in ("-h", "--help"):
        app.var.set(name)
        root.after(150, app.on_search)
    # 排查用：设了 HSFINDER_UIDUMP 就把窗口状态写出来
    dump = os.environ.get("HSFINDER_UIDUMP")
    if dump:
        def _dump():
            try:
                with open(dump, "w", encoding="utf-8") as f:
                    f.write(f"viewable={root.winfo_viewable()} "
                            f"geometry={root.winfo_geometry()} "
                            f"state={root.state()} "
                            f"title={root.title()!r} "
                            f"name_lbl={app.name_lbl.cget('text')!r}\n")
            except Exception as e:
                try:
                    with open(dump, "w", encoding="utf-8") as f:
                        f.write(f"dump failed: {e}\n")
                except Exception:
                    pass
        root.after(3000, _dump)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
