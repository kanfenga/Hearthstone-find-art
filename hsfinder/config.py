# -*- coding: utf-8 -*-
"""网络与行为参数。改这里就能调，不必翻业务代码。"""

# ---- wiki API ----
API = "https://hearthstone.wiki.gg/api.php"
REFERER = "https://hearthstone.wiki.gg/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# 单次请求超时（秒）。wiki 正常响应在 1s 内，20s 足以判定网络不可用。
TIMEOUT = 20
# 失败后的重试次数（总请求数 = RETRIES + 1）。网络差时可调大。
RETRIES = 2
# 两次请求之间至少间隔这么久（秒）。wiki 会限流，连发会收到 HTTP 429。
MIN_INTERVAL = 0.25

# ---- 预览图 ----
# 预览用的缩略图宽度。略大于常见面板宽度，缩到面板宽仍清晰；
# 同时远小于原图（原图可能十几 MB）。
PREVIEW_THUMB_WIDTH = 900
PREVIEW_TIMEOUT = 40

# ---- 缓存 ----
# 查询结果缓存文件名（放在用户缓存目录下）
CACHE_FILE = "cache.json"
# 卡名索引文件名（随程序分发）
INDEX_FILE = "names.json"

__all__ = ["API", "REFERER", "UA", "TIMEOUT", "RETRIES", "MIN_INTERVAL",
           "PREVIEW_THUMB_WIDTH", "PREVIEW_TIMEOUT", "CACHE_FILE", "INDEX_FILE"]
