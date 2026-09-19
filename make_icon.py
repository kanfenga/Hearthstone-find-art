# -*- coding: utf-8 -*-
"""make_icon.py —— 生成程序图标 icon.ico（需要 Pillow）。

画一张卡牌样式的小图标：深色描边 + 卡面渐变 + 左上角高光。
只需运行一次，产物 icon.ico 会被 hsfinder_app.py 与 build_exe.py 使用。
"""
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
SIZES = [256, 128, 64, 48, 32, 16]
BASE = 256


def rounded(draw, box, r, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def make(size=BASE):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / BASE

    def px(v):
        return int(round(v * s))

    # 卡牌底：深色描边 + 米白卡面
    rounded(d, (px(46), px(22), px(210), px(238)), px(18),
            fill=(255, 253, 246, 255), outline=(28, 30, 33, 255), width=max(1, px(7)))
    # 卡面画框
    rounded(d, (px(62), px(38), px(194), px(160)), px(10),
            fill=(58, 74, 112, 255), outline=(28, 30, 33, 255), width=max(1, px(4)))
    # 画框里的一点高光（模拟原画）
    d.ellipse((px(78), px(54), px(140), px(116)), fill=(226, 178, 92, 255))
    d.polygon([(px(62), px(160)), (px(110), px(104)), (px(150), px(150)),
               (px(176), px(128)), (px(194), px(160))], fill=(96, 132, 168, 255))
    # 下方两条"文字行"
    rounded(d, (px(66), px(176), px(190), px(192)), px(6), fill=(210, 205, 194, 255))
    rounded(d, (px(66), px(202), px(158), px(216)), px(6), fill=(224, 220, 210, 255))
    return img


def main():
    out = os.path.join(HERE, "icon.ico")
    imgs = [make(s) for s in SIZES]
    imgs[0].save(out, format="ICO", sizes=[(s, s) for s in SIZES])
    png = os.path.join(HERE, "icon.png")
    imgs[0].save(png)
    print(f"已生成 {out}（{os.path.getsize(out)/1024:.1f} KB）")
    print(f"已生成 {png}（预览用，可删）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
