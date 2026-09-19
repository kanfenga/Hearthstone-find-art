# -*- coding: utf-8 -*-
"""build_name_index.py —— 从完整卡牌数据裁出「查名索引」。

产物 names.json 只保留查名真正需要的字段（约 3 MB），供程序内嵌使用，
这样用户查中文名时无需再下载 9.9 MB 的完整卡表。

用法:
    python build_name_index.py --fetch             # 联网下载卡表并生成（推荐）
    python build_name_index.py 路径/cards_zhCN.json -o names.json
    python build_name_index.py                     # 用同目录或上一层的 cards_zhCN.json

卡表来源: https://api.hearthstonejson.com/v1/latest/zhCN/cards.json

索引结构:
    {
      "locale": "zhCN",
      "built": "2026-09-19",
      "cards": {
         "时空大盗拉法姆": {
            "id": "TIME_005", "dbfId": 119432, "type": "MINION",
            "collectible": true, "tier": [1, 1, 1, 119432],
            "others": [["HERO_07bk", "HERO"]]        # 同名但无独立原画的衍生实体
         },
         ...
      }
    }
"""
import argparse
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# 依次尝试：脚本同目录、上一层、以及老版本工具集的 _art_tools 目录
CANDIDATE_SRC = [
    os.path.join(HERE, "cards_zhCN.json"),
    os.path.join(os.path.dirname(HERE), "cards_zhCN.json"),
    os.path.join(os.path.dirname(HERE), "_art_tools", "cards_zhCN.json"),
]
DEFAULT_SRC = next((p for p in CANDIDATE_SRC if os.path.exists(p)), CANDIDATE_SRC[0])
CARD_DATA_URL = "https://api.hearthstonejson.com/v1/latest/{locale}/cards.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# 会出现在 wiki 卡片页上、有独立原画的类型
FACE_TYPES = {"MINION", "SPELL", "WEAPON", "LOCATION", "HERO", "BATTLEGROUND_SPELL"}
# 派生实体（附魔/英雄技能等），没有独立原画，只在「同名卡」提示里出现
DERIVED_TYPES = {"ENCHANTMENT", "HERO_POWER"}

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except Exception:
            pass


def card_tier(c):
    """同名卡取舍打分，越大越优先。

    非英雄 > 非衍生实体 > 可收藏 > dbfId 升序。
    英雄皮肤排最后（没有独立原画）；附魔/英雄技能同理。
    该顺序已用完整卡表里全部 6110 组同名卡评测过。
    """
    t = c.get("type")
    return (0 if t == "HERO" else 1,
            0 if t in DERIVED_TYPES else 1,
            1 if c.get("collectible") else 0,
            c.get("dbfId") or 0)


def load_source(path, locale, fetch):
    if path and os.path.exists(path):
        print(f"读本地卡表: {path}")
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    if not fetch:
        raise SystemExit(f"[!] 找不到卡表 {path}\n"
                         f"    加 --fetch 让它联网下载，或手动指定路径：\n"
                         f"      python build_name_index.py 路径/cards_zhCN.json")
    url = CARD_DATA_URL.format(locale=locale)
    print(f"联网下载卡表: {url}")
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        raw = r.read()
    print(f"  已下载 {len(raw) / 1048576:.1f} MB")
    return json.loads(raw.decode("utf-8"))


def main():
    ap = argparse.ArgumentParser(description="生成查名索引 names.json")
    ap.add_argument("source", nargs="?", default=DEFAULT_SRC, help="cards_<locale>.json 路径")
    ap.add_argument("-o", "--out", default=os.path.join(HERE, "names.json"))
    ap.add_argument("-l", "--locale", default="zhCN")
    ap.add_argument("--fetch", action="store_true", help="本地没有卡表时联网下载")
    args = ap.parse_args()

    cards = load_source(args.source, args.locale, args.fetch)
    if not isinstance(cards, list) or not cards:
        raise SystemExit("[!] 卡表内容不是非空数组，可能下坏了。")

    groups = {}
    for c in cards:
        if not isinstance(c, dict):
            continue
        name = c.get("name")
        if name:
            groups.setdefault(name, []).append(c)

    out = {}
    for name, cands in groups.items():
        best = max(cands, key=card_tier)
        if not best.get("dbfId"):
            continue
        others = sorted({(c.get("id"), c.get("type")) for c in cands
                         if c is not best and c.get("id") and c.get("type") in DERIVED_TYPES})
        out[name] = {
            "id": best.get("id"),
            "dbfId": best.get("dbfId"),
            "type": best.get("type"),
            "collectible": bool(best.get("collectible")),
            "tier": card_tier(best),
            "others": [[i, t] for i, t in others],
        }

    data = {
        "locale": args.locale,
        "built": datetime.date.today().isoformat(),
        "count": len(out),
        "cards": out,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    size = os.path.getsize(args.out)
    print(f"\n卡名 {len(out):,} 个 -> {args.out}（{size / 1024:.0f} KB）")
    for probe in ("时空大盗拉法姆", "暗影魔", "真言术：耀", "火球术"):
        v = out.get(probe)
        if v:
            extra = f"  同名衍生: {v['others']}" if v["others"] else ""
            print(f"  抽查 {probe:8s} -> {v['id']} dbfId={v['dbfId']}{extra}")


if __name__ == "__main__":
    main()
