# 炉石原画查询器（hsfinder）

> 仓库地址：<https://github.com/kanfenga/Hearthstone-find-art>
>
> 克隆：`git clone https://github.com/kanfenga/Hearthstone-find-art.git`
>
> **版本 0.9.0** —— 尚未正式发布，1.0 留给首个稳定版。

输入**卡牌中文名**，一次给出：

- 卡牌 ID、类型 / 稀有度
- 普通版 / 金卡版画师
- **异画（Signature）画师** —— 官方 API 和各大卡牌数据库都查不到这一栏，这是本工具的核心价值
- 普通版与异画的**高清全幅原画直链**和像素尺寸，左侧可预览
- **画师本人的原始发布页**（Instagram / X / ArtStation / 个人站）—— 通常比 wiki 上的更清晰
- 同名衍生卡提示（附魔、英雄技能等没有独立原画的实体）

---

## 一、怎么用

### 方式 A：双击启动器（推荐）

双击 `hsfinder-gui.cmd`，窗口打开后输入卡名，回车。

想直接查一张：

```cmd
hsfinder-gui.cmd 时空大盗拉法姆
```

### 方式 B：直接跑 Python

```cmd
python -X utf8 hsfinder_app.py
python -X utf8 hsfinder_app.py 时空大盗拉法姆
python -X utf8 hsfinder_app.py --version
```

### 界面怎么读

| 位置 | 含义 |
|---|---|
| 左侧 | 原画预览，可切换**普通版 / 异画**两个标签页 |
| 卡牌 ID / 类型 / 稀有度 | 快速确认查到的是哪张卡 |
| 普通版画师 / 异画画师 | 异画是另请画师绘制的独立作品，常与普通版不是同一人 |
| 普通版全幅 / 异画全幅 | 点链接在浏览器打开高清原图 |
| 画师原始发布 | 画师本人发的帖子，通常是全网最高清 |

底部按钮：**打开 wiki 页面**、**复制全部结果**（粘到笔记里很方便）、**清空缓存**。

快捷键：`Ctrl+L` / `Ctrl+F` 聚焦搜索框，`Ctrl+C` 复制结果（输入框未聚焦时），
`F5` 重新查询，`↑` `↓` 在候选列表里移动，`Esc` 清空输入。

### 输入什么都能认

| 输入 | 例子 |
|---|---|
| 中文名 | `时空大盗拉法姆` |
| 卡牌 ID | `TIME_005` |
| dbfId | `119432` |
| 英文页面名 | `Timethief Rafaam` |
| 名字记不全 | 输入 `拉法姆`，会弹出候选列表 |

中文名有 24,796 个已内嵌，**输入时零延迟、零下载**，输入一半就弹候选。

---

## 二、做成 exe 发给别人（对方不需要装 Python）

```cmd
python -m pip install pyinstaller
python build_exe.py              # 单文件 exe
python build_exe.py --onedir     # 目录版，启动更快
```

产物在 `dist\`：

- `炉石原画查询器.exe` —— 单文件，双击即用
- `hsfinder.exe` —— 同上的英文名副本，方便命令行调用

把这个 exe 发给别人就行，对方机器上不需要 Python、不需要 pip。
首次启动会自己解压，约 1~3 秒属于正常。

---

## 三、依赖与网络

| 项目 | 说明 |
|---|---|
| Python | 3.8+，只用标准库 + tkinter（Windows 官方安装包自带） |
| Pillow | **可选**：装了预览画质更好、缩放更快；没装会自动改用 Windows 自带的 GDI+ 解码，预览照常显示。打包 exe 时会自动带上 |
| 第三方库 | 无必装项（打包 exe 需要 PyInstaller） |
| 数据源 | [hearthstone.wiki.gg](https://hearthstone.wiki.gg) 的 Cargo / MediaWiki 公开 API |
| 缓存 | 查过的卡缓存在用户数据目录（Windows 是 `%LOCALAPPDATA%\hsfinder\cache.json`），二次查询瞬时返回 |

一次查询只发 **3 次**网络请求（画师 1 次；原画信息与画师来源并行各 1 次），
典型耗时约 1.2~1.8 秒。原画预览单独走 900px 缩略图，不会为了预览拉十几 MB 原图。

**跨机器可用性**做过的处理：

- 卡名索引随程序分发，查中文名不需要下载任何东西；
- 字体**运行时探测**，不假设你装了哪款中文字体，找不到就退回系统默认；
- 缓存目录按 `%LOCALAPPDATA%` → 程序目录的顺序找可写位置，装到只读位置也能跑；
- 界面缩放读系统 DPI，高分屏不会字小或发虚；窗口尺寸按屏幕大小自适应，
  1366×768 的小屏也放得下；
- 预览不依赖 Pillow（见上）。

---

## 四、代码结构

```
hsfinder_app.py          启动入口（参数处理 + 启动界面）
hsfinder/                主程序包
├─ meta.py               应用名与版本（单一事实来源）
├─ config.py             网络与行为参数
├─ core/                 业务核心（不含任何界面代码）
│   ├─ paths.py          应用目录、资源定位、缓存目录
│   ├─ http.py           带节流与重试的 HTTP
│   ├─ api.py            wiki.gg 的 Cargo / MediaWiki 查询
│   ├─ images.py         图片解码缩放（Pillow 或系统 GDI+）
│   ├─ index.py          卡名索引
│   └─ finder.py         查询编排与结果缓存
├─ ui/                   界面层
│   ├─ theme.py          颜色 / 字体 / 间距 设计令牌
│   ├─ widgets.py        可复用控件（卡片、按钮、链接、搜索框…）
│   ├─ preview.py        原画预览面板
│   └─ app.py            主窗口
└─ names.json            卡名索引（随程序分发）
build_name_index.py      重新生成卡名索引
build_exe.py             打包 exe
make_icon.py             生成图标（需要 Pillow）
hsfinder-gui.cmd         双击启动器（纯 ASCII）
```

**改界面**：颜色、字体、间距都在 `ui/theme.py`，不要在各处写死颜色值。
**加字段**：在 `ui/app.py` 的 `FIELDS` 里加一行，再到 `_render` 里填值即可。
**改网络行为**：超时、重试、节流间隔都在 `config.py`。
**改版本号**：只改 `hsfinder/meta.py`，窗口标题会跟着变。

---

## 五、常见问题

**Q：异画那一栏显示"该卡无签名档"？**
A：这张卡没有异画（不是所有卡都有），或者 wiki 还没记录。

**Q：普通版全幅显示"wiki 未收录全幅原稿"？**
A：部分卡（尤其早期卡、酒馆战棋、佣兵模式）wiki 没有全幅图。可以先点"画师原始发布"
碰运气，或者拿卡图去 Google Lens / Yandex 以图搜图反查画师主页。

**Q：左侧预览看不到图？**
A：预览需要把 JPEG 转码（Tk 不能直接显示 JPEG）。有 Pillow 时用它，没装则用
Windows 自带的 GDI+，两条路都不需要额外安装。若仍失败，可点右侧链接在浏览器看图。

**Q：异画预览为什么比普通版小？**
A：客户端里的异画是 2:3 竖图垫在 512×512 方画布上，有效像素只有约 295×435，
比普通版还低；异画要高清只能走画师原稿——这正是"画师原始发布"那一栏的意义。

**Q：想查的不是拉法姆系列？**
A：这个工具是通用的，任何炉石卡牌都能查。它最初是为整理拉法姆全套原画写的。

---

## 六、数据来源与许可

- 卡牌数据：[HearthstoneJSON](https://hearthstonejson.com/)（数据接口 CC0）
- 画师数据与原画链接：[Hearthstone Wiki (wiki.gg)](https://hearthstone.wiki.gg/)
- 《炉石传说》及相关素材版权归 Blizzard Entertainment 所有。
  本项目仅查询公开数据、只提供链接，不附带也不分发任何游戏素材。

License: MIT（见 `LICENSE`）
