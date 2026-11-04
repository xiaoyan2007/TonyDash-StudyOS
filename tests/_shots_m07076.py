# -*- coding: utf-8 -*-
"""渲染 Beta 1.4 返工项：浅/深两模式 × 5 页 + 作息下拉框 + 主题按钮，用于视觉自查。"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from campus_planner import core, theme  # noqa: E402
from campus_planner.main import MainWindow  # noqa: E402

theme.load_fonts()
OUT = ROOT / "tests" / "_shots" / "m07076"
OUT.mkdir(parents=True, exist_ok=True)
PAGES = ["home", "schedule", "todo", "exams", "settings"]


def settle(ms=900):
    from PySide6.QtCore import QElapsedTimer
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        app.processEvents()


def main():
    win = MainWindow()
    win.resize(1280, 820)
    data = core.sample_data()
    data.settings.onboarded = True
    win.data = data
    win._coach = None
    win.show()
    settle(300)

    for mode in ("light", "dark"):
        win.data.settings.theme_mode = mode
        win._apply_theme(rebuild=True)
        settle(700)
        for i, name in enumerate(PAGES):
            win.go(i)
            settle(320)
            path = OUT / f"{mode}_{name}.png"
            win.grab().save(str(path))
        # 作息下拉框
        win.go(4)
        settle(320)
        from campus_planner import widgets
        tps = win.settings_page.findChildren(widgets.TimePicker)
        if tps:
            tp = tps[0]
            tp.hour._open_popup()
            settle(240)
            pop = tp.hour._popup
            pop.grab().save(str(OUT / f"{mode}_timepopup.png"))
            tp.hour._popup.hide()
        # 标题栏（含主题按钮 emoji）
        win.titlebar.grab().save(str(OUT / f"{mode}_titlebar.png"))
        # 关于 / 更新日志弹窗
        from campus_planner import about_dialogs
        dlg = about_dialogs.AboutDialog(win)
        dlg.show()
        settle(240)
        dlg.grab().save(str(OUT / f"{mode}_about.png"))
        dlg.close()
        settle(120)
        print("rendered", mode)

    win.close()
    print("OUT:", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
