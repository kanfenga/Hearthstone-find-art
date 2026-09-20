# -*- coding: utf-8 -*-
"""卡名索引：中文名 / 卡牌ID / dbfId -> 卡牌信息。

索引随程序分发（names.json），所以查中文名是**零下载、零延迟**的。
"""
import json
import os

from .. import config
from .paths import cache_dir, resource_path


# 会出现在 wiki 卡片页上、有独立原画的类型
FACE_TYPES = {"MINION", "SPELL", "WEAPON", "LOCATION", "HERO", "BATTLEGROUND_SPELL"}
# 派生实体（附魔/英雄技能等），没有独立原画，只出现在「同名卡」提示里
DERIVED_TYPES = {"ENCHANTMENT", "HERO_POWER"}


def card_tier(c):
    """同名卡取舍打分，越大越优先。

    炉石里同一个中文名可能对应多张卡，取舍顺序：
    非英雄 > 非衍生实体 > 可收藏 > dbfId 升序（新版本优先）。
    英雄皮肤排最后是因为它没有独立原画；附魔/英雄技能同理。

    该顺序已用完整卡表里全部 6110 组同名卡评测过，请勿凭直觉调整。
    """
    t = c.get("type")
    return (0 if t == "HERO" else 1,
            0 if t in DERIVED_TYPES else 1,
            1 if c.get("collectible") else 0,
            -(c.get("dbfId") or 0))


class NameIndex:
    """卡名索引。优先用随程序分发的 names.json，其次用户数据目录。"""

    def __init__(self, path=None):
        self.cards = {}
        self.by_id = {}
        self.by_dbf = {}
        self.locale = "?"
        self.source = None
        self.error = None
        self._load(path)

    # -- 加载 ---------------------------------------------------------------
    def _candidates(self, path):
        if path:
            return [path]
        return [resource_path(config.INDEX_FILE),
                os.path.join(cache_dir(), config.INDEX_FILE)]

    def _load(self, path=None):
        for candidate in self._candidates(path):
            if not candidate or not os.path.exists(candidate):
                continue
            try:
                with open(candidate, encoding="utf-8") as f:
                    data = json.load(f)
                self.cards = data.get("cards") or {}
                self.locale = data.get("locale", "?")
                self.source = candidate
                break
            except Exception as e:
                self.error = f"{type(e).__name__}: {e}"
                continue
        if not self.cards and not self.error:
            self.error = f"找不到卡名索引 {config.INDEX_FILE}"
        # 反查表只建一次，避免每次查询遍历两万多个卡名
        for name, entry in self.cards.items():
            if entry.get("id"):
                self.by_id.setdefault(entry["id"], name)
            if entry.get("dbfId") is not None:
                self.by_dbf.setdefault(str(entry["dbfId"]), name)

    @property
    def ready(self):
        return bool(self.cards)

    @property
    def count(self):
        return len(self.cards)

    # -- 查询 ---------------------------------------------------------------
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
        """返回 ``(卡牌信息, 候选列表)``。text 可以是中文名 / 卡牌ID / dbfId。"""
        t = (text or "").strip()
        if not t:
            return None, []
        hit = self.cards.get(t)
        if hit:
            return hit, []
        name = self.by_id.get(t) or self.by_dbf.get(t)
        if name:
            return self.cards[name], []
        return None, self.similar(t)

    def similar(self, text, limit=20):
        """包含匹配的候选，短的优先（更像用户想找的那个）。"""
        t = (text or "").strip()
        if not t:
            return []
        out = [n for n in self.cards if t in n and n != t]
        out.sort(key=lambda n: (len(n), n))
        if t in self.cards:
            out.insert(0, t)
        return out[:limit]


__all__ = ["NameIndex", "card_tier", "FACE_TYPES", "DERIVED_TYPES"]
