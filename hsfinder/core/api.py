# -*- coding: utf-8 -*-
"""wiki.gg 的查询封装。

只关心「拿到数据」，网络细节交给 http 模块。所有函数失败时抛 ApiError。
"""
import re

from .http import api_json

URL_RE = re.compile(r"https?://[^\s\]\}<>\"|]+")


def cargo(where, fields="_pageName,artist,signatureArtist,dbfId"):
    """Cargo 查询单张卡，返回页面信息字典；查不到返回 None。

    ``signatureArtist`` 是 wiki 独有的字段 —— 官方 API 只记录普通版画师，
    异画画师只能从这里拿。
    """
    d = api_json(action="cargoquery", tables="DerivedCard", fields=fields,
                 where=where, limit=1, format="json")
    rows = d.get("cargoquery") or []
    return rows[0]["title"] if rows else None


def _norm(title):
    """把页面标题归一成可比对的键（去命名空间、下划线统一成空格）。"""
    return (title or "").replace("File:", "").replace("_", " ").strip()


def _key_map(names):
    return {_norm(n): n for n in names}


def imageinfo(filename):
    """单个 File 的图片信息；不存在返回 None。"""
    d = api_json(action="query", titles=f"File:{filename}", prop="imageinfo",
                 iiprop="url|size|mime", format="json", formatversion=2)
    pages = (d.get("query") or {}).get("pages") or []
    if not pages:
        return None
    info = (pages[0].get("imageinfo") or [None])[0]
    # wiki 对不存在的 File 有时返回字段全 null 的条目，统一归一成 None
    if not info or not info.get("url"):
        return None
    return info


def imageinfo_many(filenames):
    """一次请求查多个文件，返回 ``{文件名: 图片信息或 None}``。

    MediaWiki 支持 ``titles=A|B|C``，一次往返搞定，比逐个查快得多。
    """
    names = [f for f in filenames if f]
    if not names:
        return {}
    if len(names) == 1:
        return {names[0]: imageinfo(names[0])}
    titles = "|".join(f"File:{n}" for n in names)
    d = api_json(action="query", titles=titles, prop="imageinfo",
                 iiprop="url|size|mime", format="json", formatversion=2)
    out = {n: None for n in names}
    keys = _key_map(names)
    for p in (d.get("query") or {}).get("pages") or []:
        info = (p.get("imageinfo") or [None])[0]
        if not info or not info.get("url"):
            continue
        name = keys.get(_norm(p.get("title")))
        if name:
            out[name] = info
    return out


def sources_many(filenames):
    """一次请求取多个 File 页的 wikitext 并抠出链接。

    这里的 ``source`` 字段通常直接链到画师本人的 Instagram / X / ArtStation，
    是全网最高清的源头。
    """
    names = [f for f in filenames if f]
    if not names:
        return {}
    titles = "|".join(f"File:{n}" for n in names)
    d = api_json(action="query", titles=titles, prop="revisions",
                 rvprop="content", rvslots="main", format="json", formatversion=2)
    out = {n: [] for n in names}
    keys = _key_map(names)
    for p in (d.get("query") or {}).get("pages") or []:
        revs = p.get("revisions") or []
        content = ""
        if revs:
            content = ((revs[0].get("slots") or {}).get("main") or {}).get("content") or ""
        name = keys.get(_norm(p.get("title")))
        if name:
            out[name] = URL_RE.findall(content)
    return out


def source_of(filename):
    """单个 File 页里的发布链接。"""
    d = api_json(action="parse", page=f"File:{filename}", prop="wikitext",
                 format="json", formatversion=2)
    return URL_RE.findall(((d.get("parse") or {}).get("wikitext") or ""))


def wiki_search(text, limit=8):
    """全文搜索。用于索引里没有的名字（英文名、外号、记错的名字）。"""
    d = api_json(action="query", list="search", srsearch=text, srlimit=limit,
                 format="json")
    return [(r.get("title"), r.get("size"))
            for r in (d.get("query") or {}).get("search") or []]


def page_files_all(page):
    """列出卡片页上的全幅原稿文件名，返回 ``{"full": 名, "signature_full": 名}``。

    文件名不总是「页面名 + _full.jpg」：例如 Power Word: Glory 的实际文件是
    「Power Word- Glory full.jpg」（冒号变横线、分隔符是空格），靠拼接猜不到，
    所以猜不到时要来页面里找。一次请求把两种都取回来。
    """
    d = api_json(action="query", titles=page, prop="images", imlimit=300,
                 format="json", formatversion=2)
    pages = (d.get("query") or {}).get("pages") or []
    out = {}
    for p in pages:
        for im in p.get("images") or []:
            title = (im.get("title") or "").replace("File:", "")
            # _full.jpg / -full.jpg / " full.jpg" 都算
            if re.search(r"[\s_-]signature[\s_-]full\.jpg$", title, re.I):
                out.setdefault("signature_full", title)
            elif re.search(r"[\s_-]full\.jpg$", title, re.I):
                out.setdefault("full", title)
    return out


__all__ = ["cargo", "imageinfo", "imageinfo_many", "sources_many", "source_of",
           "wiki_search", "page_files_all", "URL_RE"]
