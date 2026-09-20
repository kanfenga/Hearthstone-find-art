# -*- coding: utf-8 -*-
"""查询编排：把「一个卡名」变成「画师 + 原画 + 来源」。

性能要点（一次查询只发 3 次网络请求）：
1. 画师：Cargo 查询 1 次；
2. 原画信息与画师来源：各自一次合并请求（``titles=A|B``），且**并行**发出；
3. 只有按页面名猜不到文件名时，才去查卡片页图片列表兜底，且整张卡只查一次。

另外：网络失败一律抛 ApiError，与「查不到这张卡」严格区分。
"""
import json
import os
import re
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from .. import config
from .api import cargo, imageinfo, imageinfo_many, page_files_all, source_of, \
    sources_many, wiki_search


class Finder:
    """查询器。线程安全性：``find`` 会并发发请求，缓存写入用锁保护。"""

    def __init__(self, index, cache_path=None):
        self.index = index
        self.cache_path = cache_path or _default_cache_path()
        self.cache = {}
        self._lock = threading.Lock()
        self._load_cache()

    # -- 缓存 ---------------------------------------------------------------
    def _load_cache(self):
        try:
            if self.cache_path and os.path.exists(self.cache_path):
                with open(self.cache_path, encoding="utf-8") as f:
                    self.cache = json.load(f)
        except Exception:
            self.cache = {}

    def save_cache(self):
        if not self.cache_path:
            return
        try:
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False)
        except Exception:
            pass                      # 缓存写不了不影响使用

    def clear_cache(self):
        with self._lock:
            self.cache = {}
        self.save_cache()

    # -- 主流程 -------------------------------------------------------------
    def find(self, text, use_cache=True, log=None):
        """查一张卡。返回结果 dict；失败时带 ``error`` 字段。"""
        say = log or (lambda *_: None)
        t = (text or "").strip()
        if not t:
            return {"error": "请输入卡牌中文名"}

        key = t.lower()
        if use_cache:
            with self._lock:
                cached = self.cache.get(key)
            if cached is not None:
                say("命中本地缓存")
                return cached

        info, cands = self.index.lookup(t)
        row = self._resolve_row(t, info, say)
        if row is None:
            return self._not_found(t, info, cands)

        page = row["_pageName"]
        result = self._build_result(t, info, row, page)
        self._attach_images(result, page)

        if use_cache:
            with self._lock:
                self.cache[key] = result
            self.save_cache()
        return result

    # -- 步骤 ---------------------------------------------------------------
    def _resolve_row(self, text, info, say):
        """拿到 wiki 上的卡片页信息；找不到返回 None。"""
        if info and info.get("dbfId"):
            where = f'dbfId="{info["dbfId"]}"'
        elif text.isdigit():
            where = f'dbfId="{text}"'
        else:
            where = f'_pageName="{text.replace("_", " ")}"'

        say("查询 wiki 画师数据…")
        row = cargo(where)
        if not row and "_" in text:
            row = cargo(f'_pageName="{text.replace("_", " ")}"')
        if not row and not info:
            # 索引里没有：先让 wiki 搜索一次，再拿搜到的页面名去查
            # （覆盖英文名、外号、以及记错的中文名）
            say("索引里没有，改用 wiki 搜索…")
            for title, _size in wiki_search(text)[:4]:
                row = cargo(f'_pageName="{title}"')
                if row:
                    break
        return row

    def _not_found(self, text, info, cands):
        if info:
            others = info.get("others") or []
            hint = "、".join(f"{i}({t.lower()})" for i, t in others[:6])
            msg = "在 wiki 上没找到这张卡"
            if hint:
                msg += f"（同名卡还有 {hint}，这些没有独立原画）"
            return {"query": text, "error": msg}
        if text.isdigit():
            return {"query": text, "error": f"wiki 上没有 dbfId={text} 这张卡"}
        hits = [h[0] for h in wiki_search(text)[:8]] if text else []
        if hits:
            return {"query": text, "error": "wiki 上有相关页面，但没有对应的卡牌数据",
                    "candidates": hits}
        return {"query": text,
                "error": "未找到该卡；若这是中文名，请改用英文页面名或卡牌 ID"}

    def _build_result(self, text, info, row, page):
        """把 wiki 行整理成结果结构（不含原画）。"""
        base = page.replace(" ", "_")
        try:
            dbf = int(row.get("dbfId"))
        except (TypeError, ValueError):
            dbf = row.get("dbfId")
        return {
            "query": text,
            "name": (info or {}).get("name"),
            "name_zh": self.index.name_of(info),
            "card_id": (info or {}).get("id"),
            "type": (info or {}).get("type"),
            "rarity": (info or {}).get("rarity"),
            "type_rarity": _type_rarity(info),
            "dbfId": dbf,
            "page": page,
            "wiki": f"https://hearthstone.wiki.gg/wiki/{urllib.parse.quote(base)}",
            "artist": row.get("artist") or None,
            # Cargo 里签名画师为空字符串 = wiki 未记录该卡有异画
            "signature_artist": (row.get("signatureArtist") or "").strip() or None,
            "others": (info or {}).get("others") or [],
            "images": {},
        }

    def _attach_images(self, result, page):
        """并行取原画信息与画师来源，再挑出实际存在的文件。"""
        base = page.replace(" ", "_")
        # 页面名可能带消歧义括号（如 "Fireball (Core)"），图片文件名通常不带
        base_alt = re.sub(r"\s*\([^)]*\)", "", page).replace(" ", "_")

        names_main = [f"{base}_full.jpg"]
        names_sig = [f"{base}_signature_full.jpg"]
        if base_alt and base_alt != base:
            names_main.append(f"{base_alt}_full.jpg")
            names_sig.append(f"{base_alt}_signature_full.jpg")
        all_names = names_main + names_sig

        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_info = pool.submit(imageinfo_many, all_names)
            fut_src = pool.submit(sources_many, all_names)
            try:
                infos = fut_info.result()
            except Exception:
                infos = {}
            try:
                srcs = fut_src.result()
            except Exception:
                srcs = {}

        fallback = {}

        def pick(candidates, kind):
            """挑第一个真实存在的候选；都不存在才去页面图片列表兜底。"""
            for name in candidates:
                if infos.get(name):
                    return name, infos[name]
            if "files" not in fallback:
                try:
                    fallback["files"] = page_files_all(page)
                except Exception:
                    fallback["files"] = {}
            real = (fallback["files"] or {}).get(kind)
            if not real:
                return None, None
            got = infos.get(real)
            if not got:
                try:
                    got = imageinfo(real)
                except Exception:
                    return None, None
            if got and real not in srcs:
                try:
                    srcs[real] = source_of(real)
                except Exception:
                    pass
            return (real, got) if got else (None, None)

        for tag, names, kind in (("regular", names_main, "full"),
                                 ("signature", names_sig, "signature_full")):
            fname, meta = pick(names, kind)
            if not meta:
                result["images"][tag] = None
                continue
            result["images"][tag] = {
                "file": fname,
                "width": meta.get("width"),
                "height": meta.get("height"),
                "url": meta.get("url"),
                "sources": srcs.get(fname) or [],
            }


def _default_cache_path():
    from .paths import cache_file
    return cache_file()


def _type_rarity(info):
    """把索引里的类型与稀有度拼成一行可读文字（索引没有就留空）。"""
    if not info:
        return None
    type_names = {"MINION": "随从", "SPELL": "法术", "WEAPON": "武器",
                  "LOCATION": "地标", "HERO": "英雄", "HERO_POWER": "英雄技能",
                  "ENCHANTMENT": "附魔", "BATTLEGROUND_SPELL": "酒馆法术"}
    rarity_names = {"FREE": "免费", "COMMON": "普通", "RARE": "稀有",
                    "EPIC": "史诗", "LEGENDARY": "传说"}
    parts = []
    if info.get("type"):
        parts.append(type_names.get(info["type"], info["type"]))
    if info.get("rarity"):
        parts.append(rarity_names.get(info["rarity"], info["rarity"]))
    if info.get("collectible") is False:
        parts.append("不可收藏")
    return " · ".join(parts) if parts else None


__all__ = ["Finder"]
