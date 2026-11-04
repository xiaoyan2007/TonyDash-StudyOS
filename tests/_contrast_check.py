# -*- coding: utf-8 -*-
"""离屏渲染后做程序化对比度自查。

对每个可见 QLabel：从它自己的截图里取「最常见的、且与声明前景色不相近」的颜色作为背景，
再按 WCAG 公式算对比度。可避开文字本身被当成背景的采样陷阱。
"""
import os
import re
import sys
from collections import Counter
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

app = QApplication(sys.argv)

from campus_planner import core, theme  # noqa: E402
from campus_planner.main import MainWindow  # noqa: E402

theme.load_fonts()
PAGES = ["home", "schedule", "todo", "exams", "settings"]


def _lum(rgb):
    def f(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def dist(a, b):
    return max(abs(a[i] - b[i]) for i in range(3))


def fg_of(w):
    ss = w.styleSheet() or ""
    m = re.search(r"color:\s*#([0-9a-fA-F]{6})", ss)
    if not m:
        return None
    h = m.group(1)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def main():
    win = MainWindow()
    win.resize(1280, 820)
    win.data = core.sample_data()
    win.show()
    app.processEvents()

    bad = []
    checked = 0
    for mode in ("light", "dark"):
        win.data.settings.theme_mode = mode
        win._apply_theme(rebuild=True)
        app.processEvents()
        for i, name in enumerate(PAGES):
            win.go(i)
            for _ in range(40):
                app.processEvents()
            for lab in win.findChildren(QLabel):
                if not lab.isVisible() or not lab.text().strip():
                    continue
                if lab.width() < 8 or lab.height() < 8:
                    continue
                fg = fg_of(lab)
                if fg is None:
                    continue
                img = lab.grab().toImage()
                w, h = img.width(), img.height()
                colors = Counter()
                for yy in range(0, h, max(1, h // 20)):
                    for xx in range(0, w, max(1, w // 40)):
                        c = img.pixelColor(xx, yy)
                        colors[(c.red(), c.green(), c.blue())] += 1
                if not colors:
                    continue
                bg = None
                for col, _n in colors.most_common():
                    if dist(col, fg) > 70:
                        bg = col
                        break
                if bg is None:
                    continue
                checked += 1
                ratio = contrast(fg, bg)
                if ratio < 3.0:
                    bad.append((round(ratio, 2), mode, name,
                                lab.text().replace("\n", " ")[:30], fg, bg))
    bad.sort()
    print(f"检查 {checked} 个标签；低于 3.0 的 {len(bad)} 个")
    for row in bad[:40]:
        print("   ", row)
    win.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
