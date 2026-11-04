# -*- coding: utf-8 -*-
"""切主题后检查是否还有浅色残留：遍历控件树，找仍写着浅色主题字面量的样式表。"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QLabel, QWidget  # noqa: E402

app = QApplication(sys.argv)

from campus_planner import core, theme  # noqa: E402

theme.load_fonts()
theme.set_theme("light")

LIGHT_ONLY = {
    "text": theme.LIGHT["text"].lower(),
    "sub": theme.LIGHT["sub"].lower(),
    "muted": theme.LIGHT["muted"].lower(),
}
DARK = {k: v.lower() for k, v in theme.DARK.items() if isinstance(v, str)}


def walk(root):
    yield root
    for child in root.findChildren(QWidget):
        yield child


def scan(win, mode):
    leaks = []
    for w in walk(win):
        try:
            ss = w.styleSheet() or ""
        except Exception:
            continue
        if not ss:
            continue
        low = ss.lower()
        for key, val in LIGHT_ONLY.items():
            if val and val in low:
                leaks.append((type(w).__name__, getattr(w, "text", lambda: "")() [:24], key, val))
    return leaks


def main():
    from campus_planner.main import MainWindow

    win = MainWindow()
    win.resize(1280, 820)
    win.data = core.sample_data()
    win.data.settings.theme_mode = "dark"
    win._apply_theme(rebuild=True)
    win.show()
    app.processEvents()

    bad = 0
    for idx in range(5):
        win.go(idx)
        app.processEvents()
        leaks = scan(win, "dark")
        name = ["home", "schedule", "todo", "exams", "settings"][idx]
        if leaks:
            bad += len(leaks)
            print(f"[dark/{name}] {len(leaks)} 处浅色残留：")
            for row in leaks[:12]:
                print("    ", row)
        else:
            print(f"[dark/{name}] OK 无浅色残留")

    # 设置页作息下拉框：确认点击能弹出（此前 _open_menu 名字写错）
    win.go(4)
    app.processEvents()
    page = win.settings_page
    tps = page.findChildren(type(page).__mro__ and __import__(
        "campus_planner.widgets", fromlist=["TimePicker"]).TimePicker)
    if tps:
        tp = tps[0]
        tp.hour._open_popup()
        app.processEvents()
        pop = tp.hour._popup
        print(f"[popup] visible={pop.isVisible()} items={pop.list.count()} "
              f"size={pop.width()}x{pop.height()}")
    else:
        print("[popup] 未找到 TimePicker")
        bad += 1

    # 主题按钮 emoji 尺寸
    btn = win.titlebar.theme_btn
    print(f"[theme_btn] size={btn.width()}x{btn.height()} icon={btn.icon_name!r} "
          f"icon_px={btn._icon_px()}")

    win.close()
    print("LEAK TOTAL:", bad)
    return 0


if __name__ == "__main__":
    sys.exit(main())
