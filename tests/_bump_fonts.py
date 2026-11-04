# -*- coding: utf-8 -*-
"""Beta 1.4 bug3：把除标题外的小字整体放大一档。

9.5 -> 11、10 -> 11.5、10.5 -> 12。只改 campus_planner 产品代码。
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = sorted(list((ROOT / "campus_planner").glob("*.py"))
               + list((ROOT / "campus_planner" / "pages").glob("*.py")))

# 顺序很重要：先长后短，避免 10 抢先命中 10.5
THEME_RULES = [
    ("theme.font(9.5", "theme.font(11"),
    ("theme.font(10.5", "theme.font(12"),
    ("theme.font(10,", "theme.font(11.5,"),
    ("theme.font(10)", "theme.font(11.5)"),
]
# widgets.label(文本, 字号, ...) 的第二个位置参数
LABEL_RE = re.compile(r"(widgets\.label\([^,]+,\s*)(\d+(?:\.\d+)?)(?=[,\)])")

LABEL_MAP = {"9.5": "11", "10": "11.5", "10.5": "12"}

for path in FILES:
    text = path.read_text(encoding="utf-8")
    original = text
    for old, new in THEME_RULES:
        text = text.replace(old, new)

    def _bump(match):
        size = match.group(2)
        return match.group(1) + LABEL_MAP.get(size, size)

    text = LABEL_RE.sub(_bump, text)
    if text != original:
        path.write_text(text, encoding="utf-8")
        print("updated", path.name)
