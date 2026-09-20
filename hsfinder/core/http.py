# -*- coding: utf-8 -*-
"""带节流与重试的 HTTP 客户端。

两个坑：

1. **限流**：wiki 对连发请求返回 HTTP 429。这里在两次请求之间强制间隔，
   并在收到 429 时退避重试。
2. **错误语义**：网络失败必须和「查不到这张卡」区分开，否则断网会被
   误报成卡不存在。所有失败一律抛 ``ApiError``。
"""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .. import config

# 节流状态：用锁串行化「决定何时发」这一段，避免多线程同时打。
# 注意锁只覆盖计时，不覆盖网络 I/O，所以并行请求仍然并行。
_rate_lock = threading.Lock()
_last_call = [0.0]


class ApiError(Exception):
    """网络层失败（不可达 / HTTP 错误 / 返回不可解析）。"""


def _throttle():
    with _rate_lock:
        gap = time.monotonic() - _last_call[0]
        if gap < config.MIN_INTERVAL:
            time.sleep(config.MIN_INTERVAL - gap)
        _last_call[0] = time.monotonic()


def http_get(url, timeout=None, headers=None):
    """GET 并返回原始字节。"""
    h = {"User-Agent": config.UA, "Referer": config.REFERER}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout or config.TIMEOUT) as r:
        return r.read()


def api_json(params=None, timeout=None, retries=None, **extra):
    """调用 MediaWiki API 并返回解析后的 JSON。

    参数可以直接写成关键字（``action="query", titles=...``），
    也可以整体传一个 dict 给 ``params``。

    失败时抛 ApiError，绝不返回空结果 —— 这点很重要，
    否则调用方无法区分「网络坏了」和「wiki 上没有这条数据」。
    """
    query = dict(params or {})
    query.update(extra)
    timeout = timeout or config.TIMEOUT
    retries = config.RETRIES if retries is None else retries
    qs = urllib.parse.urlencode(query)
    url = f"{config.API}?{qs}"
    deadline = time.monotonic() + timeout * (retries + 1) + 12
    last = None
    for attempt in range(retries + 1):
        if time.monotonic() > deadline:
            break
        _throttle()
        try:
            raw = http_get(url, timeout=timeout).decode("utf-8", "replace")
            return json.loads(raw)
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code} {e.reason}"
            if e.code == 429:                       # 被限流：退避后重试
                time.sleep(1.5 + 2.5 * attempt)
                continue
            if e.code in (403, 404):                # 重试无意义
                break
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
        time.sleep(0.8 + attempt)
    if last and "429" in last:
        raise ApiError("查询太频繁，被 wiki 限流了，请等几秒再试")
    raise ApiError(f"连不上 wiki（{last}）")


__all__ = ["ApiError", "http_get", "api_json"]
