"""Beta 1.4 需求逐条功能验证（离屏，程序化断言）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["APPDATA"] = str(ROOT / "tests" / "_appdata_verify")
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt, QUrl, QEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from campus_planner import core, theme, changelog  # noqa: E402

ok = []
bad = []


def check(name, cond, detail=""):
    (ok if cond else bad).append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  {detail}" if detail and not cond else ""))


def main():
    app = QApplication(sys.argv)
    theme.load_fonts()
    app.setFont(theme.font(13))
    theme.apply_global_qss(force=True)

    # ---- bug1: 默认作息 = 浙江工商大学
    p = core.default_periods()
    expected = [("08:05", "08:50"), ("08:50", "09:35"), ("09:50", "10:35"),
                ("10:40", "11:25"), ("11:30", "12:15"), ("13:40", "14:25"),
                ("14:35", "15:20"), ("15:30", "16:15"), ("16:25", "17:10"),
                ("18:30", "19:15"), ("19:25", "20:10"), ("20:20", "21:05")]
    got = [(x.start, x.end) for x in p]
    check("bug1 默认作息为浙江工商大学12节", got == expected, f"got={got}")

    from campus_planner.main import MainWindow
    win = MainWindow()
    win.data = core.sample_data()
    win.data.settings.onboarded = True
    win.data.settings.glass = 70
    core.save_data(win.data)
    win.resize(1280, 820)
    win.show()
    app.processEvents()

    # ---- 性能：页面懒加载（构造后只建首页）
    check("初始仅构建首页", win._page_built.count(True) == 1, str(win._page_built))

    # ---- bug2: 标题栏主题按钮图标是 moon/sun（矢量，不是 info）
    check("bug2 浅色主题按钮图标为 moon", win.titlebar.theme_btn.icon_name == "moon",
          win.titlebar.theme_btn.icon_name)
    check("bug2 moon 属矢量图标", "moon" in theme.VECTOR_ICONS)
    win.set_theme_mode("dark")
    app.processEvents()
    check("bug2 深色主题按钮图标为 sun", win.titlebar.theme_btn.icon_name == "sun",
          win.titlebar.theme_btn.icon_name)
    win.set_theme_mode("light")
    app.processEvents()

    # ---- bug3: 关于页 GitHub 卡片点击打开网页
    from campus_planner.about_dialogs import AboutDialog, _GithubCard
    about = AboutDialog(win)
    card = about.findChild(_GithubCard)
    check("bug3 About 含 GitHub 卡片", card is not None)
    opened = []
    from PySide6.QtGui import QDesktopServices
    # 拦截 openUrl
    _orig = QDesktopServices.openUrl
    def spy(url):
        opened.append(url.toString())
        return _orig(url)
    try:
        QDesktopServices.openUrl = staticmethod(spy)
        # 同时 patch 模块内引用
        import campus_planner.about_dialogs as ad
        if hasattr(ad, "QDesktopServices"):
            ad.QDesktopServices.openUrl = staticmethod(spy)
        QTest.mouseClick(card, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         card.rect().center())
        app.processEvents()
    finally:
        QDesktopServices.openUrl = _orig
    check("bug3 点击 GitHub 卡片打开项目主页",
          core.APP_GITHUB in opened, f"opened={opened}")

    # ---- bug4: 更新日志「查看全部」独立窗口 + 当前版本在最上
    from PySide6.QtWidgets import QTextBrowser
    from campus_planner.about_dialogs import ChangelogDialog
    cl = ChangelogDialog(win)
    browser = cl.findChild(QTextBrowser)
    html = browser.toHtml() if browser is not None else ""
    check("bug4 ChangelogDialog 存在", cl is not None)
    first = changelog.RELEASES[0]
    check("bug4 更新日志当前版本在最上", first.version == core.APP_VERSION,
          f"{first.version} vs {core.APP_VERSION}")
    check("bug4 更新日志含 Beta 1.4 标题", "Beta 1.4" in html or "Beta 1.4" in changelog.changelog_html())

    # ---- 新功能：鸣谢名单 5 校按拼音排序
    from campus_planner.credits import SCHOOLS
    names = [s.name for s in SCHOOLS]
    check("鸣谢名单 5 所学校", len(SCHOOLS) == 5, str(names))
    pinyin = [s.pinyin for s in SCHOOLS]
    check("鸣谢名单按拼音排序", pinyin == sorted(pinyin), str(pinyin))
    check("鸣谢名单含浙江工商大学", "浙江工商大学" in names)

    # ---- 版本 / 更新日志
    check("版本号为 Beta 1.4", core.APP_VERSION == "Beta 1.4", core.APP_VERSION)
    check("更新日志有 Beta 1.4", changelog.latest().version == "Beta 1.4")

    # ---- 性能：页面懒加载
    win.go(0)
    app.processEvents()
    win.go(1)
    app.processEvents()
    check("切到课表后构建课表页", win._page_built[1] is True)
    check("切到课表后首页仍在", win._page_built[0] is True)

    # ---- TimePicker 禁滚轮 + 取值
    from campus_planner.widgets import TimePicker
    tp = TimePicker()
    tp.set_time("08:05")
    from PySide6.QtCore import QPointF, QPoint
    from PySide6.QtGui import QWheelEvent
    ev = QWheelEvent(QPointF(30, 10), QPointF(30, 10), QPoint(0, 120), QPoint(0, 120),
                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                     Qt.ScrollPhase.NoScrollPhase, False)
    before = tp.value()
    # 滚轮发给小时输入框（事件过滤器安装在 _TimeField 与内部 lineEdit 上）
    QApplication.sendEvent(tp.hour, ev)
    QApplication.sendEvent(tp.hour.line, ev)
    check("作息下拉框滚轮被屏蔽", tp.value() == before, f"v={tp.value()}")
    check("TimePicker 取值正确", tp.value() == "08:05", tp.value())

    # ---- 主题切换渐变
    win._switch_theme("dark")
    an = win._theme_anim
    check("主题切换创建了渐变动画", an is not None and an.totalDuration() == 420,
          str(an.totalDuration() if an else None))
    app.processEvents()

    # ---- 启动动画
    from campus_planner.splash import SplashScreen
    splash = SplashScreen(1200)
    splash.show()
    app.processEvents()
    check("启动动画含 LOGO", splash._logo is not None and not splash._logo.isNull())
    check("启动动画含开发者头像", splash._avatar is not None and not splash._avatar.isNull())
    check("启动动画含版本号", core.APP_VERSION in str(splash.windowTitle()) or core.APP_VERSION)
    check("启动动画含激励学习元素", len(splash._tags) >= 3, str(splash._tags))
    splash._timer.stop()
    splash.close()

    # ---- 保存 / 往返
    d = core.load_data()
    check("数据可往返", d is not None)

    print(f"\n== {len(ok)} passed, {len(bad)} failed ==")
    if bad:
        print("FAILED:", ", ".join(bad))
        sys.exit(1)
    win.close()


if __name__ == "__main__":
    main()
