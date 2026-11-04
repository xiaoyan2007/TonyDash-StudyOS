# -*- coding: utf-8 -*-
"""把 大学logo/ 下的真实校徽裁剪为鸣谢栏可用的透明 PNG。

规则（用户 m06034）：
- 圆形 logo（云南/浙江工商/浙江财经/澳门）：去掉圆以外的白色部分 → 圆形遮罩 + 透明。
- 宁波诺丁汉：保留原图形状，只裁到内容包围盒（不做圆形化）。
输出到 assets/credits/<缩写>.png，供 credits.py 的 _badge_pixmap 优先加载。
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
LOGO_DIR = ROOT / "大学logo"
OUT_DIR = ROOT / "assets" / "credits"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MAPPING = [
    ("云南大学.png", "YNU"),
    ("浙江工商大学.png", "ZJGSU"),
    ("浙江财经大学.png", "ZUFE"),
    ("澳门大学.png", "UM"),
    ("宁波诺丁汉大学.png", "UNNC"),
]
CIRCLE = {"YNU", "ZJGSU", "ZUFE", "UM"}


def content_bbox(img: Image.Image):
    a = np.array(img.convert("RGBA"))
    nonwhite = (a[:, :, 0] < 240) | (a[:, :, 1] < 240) | (a[:, :, 2] < 240)
    if not nonwhite.any():
        return None
    ys, xs = np.where(nonwhite)
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def circle_crop(crop: Image.Image, size=256):
    w, h = crop.size
    s = min(w, h)
    cx, cy = w // 2, h // 2
    left = cx - s // 2
    top = cy - s // 2
    sq = crop.crop((left, top, left + s, top + s)).convert("RGBA")
    # 高分辨率遮罩，缩小后得到平滑边缘
    big = max(s, 8) * 4
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, big - 1, big - 1), fill=255)
    mask = mask.resize((s, s), Image.LANCZOS)
    out = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    out.paste(sq.resize((s, s), Image.LANCZOS), (0, 0), mask)
    return out.resize((size, size), Image.LANCZOS)


def main():
    for fname, abbr in MAPPING:
        p = LOGO_DIR / fname
        if not p.exists():
            print(f"[跳过] 找不到 {p}")
            continue
        img = Image.open(p).convert("RGBA")
        bbox = content_bbox(img)
        if bbox is None:
            print(f"[跳过] {fname} 全白")
            continue
        crop = img.crop(bbox)
        w, h = crop.size
        if abbr in CIRCLE:
            out = circle_crop(crop, size=256)
            out.save(OUT_DIR / f"{abbr}.png")
            print(f"[圆形] {fname} -> {abbr}.png  bbox={bbox} src={w}x{h} -> 256x256 透明圆")
        else:
            # 诺丁汉：保留原图形状，仅裁到内容包围盒；限制最大边
            max_side = 256
            if max(w, h) > max_side:
                scale = max_side / float(max(w, h))
                crop = crop.resize(
                    (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
                    Image.LANCZOS)
            crop.save(OUT_DIR / f"{abbr}.png")
            print(f"[原图] {fname} -> {abbr}.png  bbox={bbox} src={w}x{h} -> {crop.size}")


if __name__ == "__main__":
    sys.exit(main())
