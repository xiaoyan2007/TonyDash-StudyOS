"""生成 README 与 assets/screens 用的界面截图（离屏渲染）。

用法：py tests/make_screens.py
产物直接写入 assets/screens/，含 Beta 1.5 的全部新页面。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["APPDATA"] = str(ROOT / "tests" / "_shots_appdata")
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QDate  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from campus_planner import core, theme  # noqa: E402

OUT = ROOT / "assets" / "screens"


def wait(app, n=10):
    for _ in range(n):
        app.processEvents()


def main():
    app = QApplication(sys.argv)
    theme.load_fonts()
    app.setFont(theme.font(13))
    theme.apply_global_qss(force=True)

    import shutil
    shutil.rmtree(ROOT / "tests" / "_shots_appdata", ignore_errors=True)

    from campus_planner.main import MainWindow

    win = MainWindow()
    win.resize(1240, 800)
    win.show()
    wait(app)
    # 示例数据：课程、考试、待办齐全，截图才有内容
    win.data = core.sample_data()
    win.data.settings.onboarded = True
    win.week = core.current_week(
        win.data.settings.term_start, win.data.settings.total_weeks)
    core.save_data(win.data)
    win._refresh_pages()
    wait(app)

    # 0 主页（时间屏幕 + Beta 1.5 标题理念副标题）
    win.go(0)
    wait(app, 14)
    win.grab().save(str(OUT / "home.png"))
    print("home.png")

    # 1 课程表（含「导入课表」按钮）
    win.go(1)
    wait(app, 14)
    win.grab().save(str(OUT / "schedule.png"))
    print("schedule.png")

    # 2 待办
    win.go(2)
    wait(app, 14)
    win.grab().save(str(OUT / "todo.png"))
    print("todo.png")

    # 3 期末考试
    win.go(3)
    wait(app, 14)
    win.grab().save(str(OUT / "exams.png"))
    print("exams.png")

    # 4 课表导入（直接实例化页面，不依赖文件解析）
    win.go(4)
    wait(app, 14)
    win.grab().save(str(OUT / "import.png"))
    print("import.png")

    # 5 词典查询
    win.go(5)
    wait(app, 14)
    win.grab().save(str(OUT / "lookup.png"))
    print("lookup.png")

    # 6 单词本
    win.go(6)
    wait(app, 14)
    win.grab().save(str(OUT / "wordbook.png"))
    print("wordbook.png")

    # 7 设置
    win.go(7)
    wait(app, 14)
    win.grab().save(str(OUT / "settings.png"))
    print("settings.png")

    # 关于弹窗
    from campus_planner.about_dialogs import AboutDialog, ChangelogDialog
    d = AboutDialog(win)
    d.show(); wait(app, 12)
    d.grab().save(str(OUT / "about.png")); d.close()
    print("about.png")

    d = ChangelogDialog(win)
    d.show(); wait(app, 12)
    d.grab().save(str(OUT / "changelog.png")); d.close()
    print("changelog.png")

    win.close()
    shutil.rmtree(ROOT / "tests" / "_shots_appdata", ignore_errors=True)
    print("ALL DONE ->", OUT)


if __name__ == "__main__":
    main()
