# -*- coding: utf-8 -*-
"""应用标识 —— 名称与版本号只在这里定义一处。"""

APP_NAME = "hsfinder"
APP_TITLE = "炉石原画查询器"
# 尚未正式发布：1.0 留给首个稳定版，之前一直用 0.x
VERSION = "0.9.0"
DESCRIPTION = "输入卡牌中文名，查到画师与最高清原画"

# 缓存目录名（放在用户数据目录下）
CACHE_FOLDER = "hsfinder"

__all__ = ["APP_NAME", "APP_TITLE", "VERSION", "DESCRIPTION", "CACHE_FOLDER"]
