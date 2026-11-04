# -*- coding: utf-8 -*-
"""从大学logo/宁波诺丁汉大学.png 裁出圆形校徽（城堡居中），写入 assets/credits/UNNC.png。"""
import os
import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "大学logo", "宁波诺丁汉大学.png")
OUT = os.path.join(ROOT, "assets", "credits", "UNNC.png")
SIZE = 256


def main():
    im = Image.open(SRC).convert("RGBA")
    a = np.array(im)
    dark = (a[:, :, 0] < 200) & (a[:, :, 1] < 200) & (a[:, :, 2] < 200)
    dark[:, :10] = False          # 去掉左侧边框线
    dark[-10:, :] = False
    ys, xs = np.nonzero(dark)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    print(f"content bbox x {x0}-{x1} y {y0}-{y1}")

    # 城堡 = 上半部分里最宽的一段（取 y 前 55% 范围内的暗像素）
    split = y0 + int((y1 - y0) * 0.55)
    top = dark.copy()
    top[split:, :] = False
    tys, txs = np.nonzero(top)
    cx = int((txs.min() + txs.max()) / 2)
    cy = int((tys.min() + tys.max()) / 2)
    half = max(txs.max() - txs.min(), tys.max() - tys.min()) / 2.0
    radius = int(min(118, max(46, half * 1.55)))
    print(f"castle center ({cx},{cy}) radius {radius}")

    left = max(0, cx - radius)
    top_ = max(0, cy - radius)
    right = min(im.width, cx + radius)
    bottom = min(im.height, cy + radius)
    box = (left, top_, right, bottom)
    print("crop box", box)

    crop = im.crop(box)
    w, h = crop.size
    scale = SIZE / min(w, h)
    crop = crop.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    w, h = crop.size
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ox = (SIZE - w) // 2
    oy = (SIZE - h) // 2
    canvas.paste(crop, (ox, oy), crop)

    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, SIZE - 1, SIZE - 1), fill=255)
    canvas.putalpha(mask)
    canvas.save(OUT)
    print("saved", OUT, canvas.size)

    # 复核：城堡中心是否落在画布中心
    arr = np.array(canvas)
    center = arr[SIZE // 2, SIZE // 2]
    print("center px", center)


if __name__ == "__main__":
    main()
