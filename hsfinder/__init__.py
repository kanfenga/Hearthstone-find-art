# -*- coding: utf-8 -*-
"""hsfinder —— 炉石原画查询器。

包结构：

    hsfinder/
    ├─ meta.py        应用名、版本等单一事实来源
    ├─ config.py      网络与行为参数
    ├─ core/
    │   ├─ paths.py   应用目录、资源定位、缓存目录（跨机器可用）
    │   ├─ http.py    带节流与重试的 HTTP
    │   ├─ api.py     wiki.gg 的 Cargo / MediaWiki 查询
    │   ├─ images.py  图片解码与缩放（Pillow 或系统 GDI+）
    │   ├─ index.py   卡名索引
    │   └─ finder.py  查询编排与结果缓存
    └─ ui/
        ├─ theme.py   颜色 / 字体 / 间距 设计令牌
        ├─ widgets.py 可复用控件
        ├─ preview.py 原画预览面板
        └─ app.py     主窗口

对外的稳定入口是 ``run()``：启动图形界面。
"""
from .meta import APP_NAME, APP_TITLE, VERSION

__all__ = ["APP_NAME", "APP_TITLE", "VERSION", "run"]


def run(cli_args=None):
    """启动图形界面（延迟导入，避免仅取版本号时也去加载 tkinter）。"""
    from .ui.app import run as _run
    return _run(cli_args)
