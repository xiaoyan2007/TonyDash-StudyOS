"""Beta 1.4 补充截图：启动动画、标题栏主题按钮、鸣谢名单、关于/更新日志、主题渐变。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["APPDATA"] = str(ROOT / "tests" / "_appdata_b14b")
SHOTS = ROOT / "tests" / "_shots" / "b14b"
SHOTS.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from campus_planner import core, theme  # noqa: E402


def main():
    global app
    app = QApplication(sys.argv)
    theme.load_fonts()
    app.setFont(theme.font(13))
    theme.apply_global_qss(force=True)

    # 1) 启动动画帧（用真实 elapsed 驱动，逐帧 grab）
    from campus_planner.splash import SplashScreen
    import time as _time
    splash = SplashScreen(3000)
    splash.resize(560, 360)
    splash.show()
    app.processEvents()
    splash._elapsed.start()
    for t, name in [(0.20, "splash_020"), (0.60, "splash_060"), (1.20, "splash_120"),
                    (2.00, "splash_200"), (2.60, "splash_260")]:
        while splash._elapsed.elapsed() / 1000.0 < t:
            app.processEvents()
            _time.sleep(0.01)
        splash.grab().save(str(SHOTS / f"{name}.png"))
        print("saved", name)
    splash._timer.stop()
    splash.close()

    # 2) 主窗口：标题栏主题按钮 + 鸣谢名单 + 主题渐变
    from campus_planner.main import MainWindow
    win = MainWindow()
    win.data = core.sample_data()
    win.data.settings.onboarded = True
    win.week = core.current_week(win.data.settings.term_start,
                                 win.data.settings.total_weeks)
    win.data.settings.glass = 70
    core.save_data(win.data)
    win._refresh_pages()
    win.resize(1280, 820)
    win.show()
    app.processEvents()

    def settle(ms=260):
        """等主题交叉渐变动画结束、背景重建完成再抓图。"""
        for _ in range(int(ms / 8) + 1):
            if win._theme_anim is not None and win._theme_anim.state() == 2:
                app.processEvents()
                _time.sleep(0.008)
                continue
            app.processEvents()
            _time.sleep(0.008)

    win.set_theme_mode("light")
    settle()
    win.grab().save(str(SHOTS / "titlebar_light.png"))
    print("saved titlebar_light")
    win.set_theme_mode("dark")
    settle()
    win.grab().save(str(SHOTS / "titlebar_dark.png"))
    print("saved titlebar_dark")

    # 主题渐变中间帧
    win.set_theme_mode("light")
    settle()
    win._switch_theme("dark")
    for mid, name in [(0.25, "theme_mid_25"), (0.60, "theme_mid_60")]:
        an = win._theme_anim
        while an is not None and an.state() == 2 and an.currentTime() / max(1, an.totalDuration()) < mid:
            app.processEvents()
            _time.sleep(0.01)
        win.grab().save(str(SHOTS / f"{name}.png"))
        print("saved", name)
    settle()
    win.grab().save(str(SHOTS / "theme_done.png"))
    print("saved theme_done")

    # 3) 鸣谢名单（设置页底部）
    win.go(4)
    app.processEvents()
    bar = win.settings_page.scroll.verticalScrollBar()
    bar.setValue(bar.maximum())
    app.processEvents()
    win.set_theme_mode("light")
    settle()
    bar.setValue(bar.maximum())
    app.processEvents()
    win.grab().save(str(SHOTS / "credits_light.png"))
    print("saved credits_light")
    win.set_theme_mode("dark")
    settle()
    bar.setValue(bar.maximum())
    app.processEvents()
    win.grab().save(str(SHOTS / "credits_dark.png"))
    print("saved credits_dark")

    # 4) 关于 / 更新日志
    win.set_theme_mode("light")
    app.processEvents()
    from campus_planner.about_dialogs import AboutDialog, ChangelogDialog
    about = AboutDialog(win)
    about.show()
    app.processEvents()
    about.grab().save(str(SHOTS / "about_light.png"))
    print("saved about_light")
    about.close()
    cl = ChangelogDialog(win)
    cl.show()
    app.processEvents()
    cl.grab().save(str(SHOTS / "changelog_light.png"))
    print("saved changelog_light")
    cl.close()

    win.close()
    print("done")


if __name__ == "__main__":
    main()
