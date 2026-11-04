"""Beta 1.4 离屏截图：浅色/深色 × 五个页面 + 窄屏 + 作息时间选择器。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["APPDATA"] = str(ROOT / "tests" / "_appdata_b14")
SHOTS = ROOT / "tests" / "_shots"
SHOTS.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from campus_planner import core, theme  # noqa: E402

PAGES = [("home", 0), ("schedule", 1), ("todo", 2), ("exams", 3), ("settings", 4)]


def render_one(win, name, mode, shots_dir, width=1280, height=820):
    win.resize(width, height)
    win.show()
    app.processEvents()
    for label, idx in PAGES:
        win.go(idx)
        app.processEvents()
        path = shots_dir / f"{mode}_{name}_{label}.png"
        win.grab().save(str(path))
        print("saved", path.name)


def main():
    global app
    app = QApplication(sys.argv)
    theme.load_fonts()
    app.setFont(theme.font(13))
    theme.apply_global_qss(force=True)
    from campus_planner.main import MainWindow

    # 示例数据，便于看到内容
    win = MainWindow()
    win.data = core.sample_data()
    win.data.settings.onboarded = True
    win.week = core.current_week(win.data.settings.term_start,
                                 win.data.settings.total_weeks)
    win.data.settings.glass = 70
    core.save_data(win.data)
    win._refresh_pages()
    win.data.settings.theme_mode = "light"
    theme.apply_global_qss(force=True)
    win._refresh_pages()
    app.processEvents()

    light = SHOTS / "b14_light"
    dark = SHOTS / "b14_dark"
    light.mkdir(exist_ok=True)
    dark.mkdir(exist_ok=True)

    # 浅色
    theme.apply_global_qss(force=True)
    render_one(win, "main", "light", light)
    # 深色
    win.set_theme_mode("dark")
    app.processEvents()
    render_one(win, "main", "dark", dark)

    # 浅色窄屏
    theme.apply_global_qss(force=True)
    win.set_theme_mode("light")
    app.processEvents()
    render_one(win, "narrow", "light", light, width=1080, height=680)
    # 深色窄屏
    win.set_theme_mode("dark")
    app.processEvents()
    render_one(win, "narrow", "dark", dark, width=1080, height=680)

    # 作息时间选择器（设置页）：滚到作息区，抓浅色/深色
    win.set_theme_mode("light")
    app.processEvents()
    win.go(4)
    app.processEvents()
    bar = win.settings_page.scroll.verticalScrollBar()
    bar.setValue(bar.maximum())
    app.processEvents()
    win.grab().save(str(light / "light_period_picker.png"))
    print("saved light_period_picker.png")
    win.set_theme_mode("dark")
    app.processEvents()
    bar.setValue(bar.maximum())
    app.processEvents()
    win.grab().save(str(dark / "dark_period_picker.png"))
    print("saved dark_period_picker.png")
    win.close()


if __name__ == "__main__":
    main()
