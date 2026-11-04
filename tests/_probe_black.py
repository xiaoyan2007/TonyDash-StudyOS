"""精确定位弹窗里的纯黑像素：按 y 带给出 x 范围。"""
import os
import sys
from collections import Counter

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("APPDATA", "tests/_appdata_final5")
sys.path.insert(0, ".")

from PySide6.QtWidgets import QApplication  # noqa: E402

from campus_planner import theme  # noqa: E402

app = QApplication([])
theme.load_fonts()
app.setFont(theme.font(13))
app.setStyleSheet(theme.global_qss())

from campus_planner.about_dialogs import AboutDialog, ChangelogDialog  # noqa: E402


def analyse(name, cls):
    for mode in ("light", "dark"):
        theme.set_theme(mode)
        app.setStyleSheet(theme.global_qss())
        d = cls(None)
        d.show()
        app.processEvents()
        pm = d.grab()
        pm.save(f"tests/_shots/{name}_{mode}_probe.png")
        d.close()
        app.processEvents()

        from PIL import Image

        im = Image.open(f"tests/_shots/{name}_{mode}_probe.png").convert("RGB")
        w, h = im.size
        px = im.load()
        bands = {}
        for y in range(h):
            for x in range(w):
                if px[x, y] == (0, 0, 0):
                    k = y // 40
                    e = bands.setdefault(k, [0, 10 ** 9, -1])
                    e[0] += 1
                    e[1] = min(e[1], x)
                    e[2] = max(e[2], x)
        print(f"{name} {mode} {w}x{h} black={sum(v[0] for v in bands.values())}")
        for k in sorted(bands)[:8]:
            n, x0, x1 = bands[k]
            print(f"   y {k*40:4d}-{k*40+39:4d}: {n:6d} px  x[{x0},{x1}]")
        if len(bands) > 8:
            print("   ...")


analyse("about", AboutDialog)
analyse("changelog", ChangelogDialog)
print("DONE")
