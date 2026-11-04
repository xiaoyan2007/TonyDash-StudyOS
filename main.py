"""TonyDash学习终端 —— 课表 · 考试 · 待办（PySide6 桌面程序入口）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    selftest = "--selftest" in sys.argv
    if selftest:
        # 无显示环境下的打包自检：离屏渲染一帧，确认资源与依赖完整。
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication

    from campus_planner import core, theme
    from campus_planner.main import MainWindow

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName(core.APP_NAME)
    app.setApplicationDisplayName(core.APP_NAME)
    app.setOrganizationName("CampusPlanner")
    app.setApplicationVersion(core.APP_VERSION)
    theme.load_fonts()
    app.setWindowIcon(theme.app_icon(256))
    app.setFont(theme.font(13))
    theme.apply_global_qss(force=True)

    window = MainWindow()

    if selftest:
        # 无显示环境下的打包自检：离屏渲染一帧，确认资源与依赖完整。
        window.show()
        app.processEvents()
        out = Path.cwd() / "selftest.png"
        ok = window.grab().save(str(out))

        window.go(3)
        app.processEvents()
        todo_out = Path.cwd() / "selftest_todo.png"
        ok = window.grab().save(str(todo_out)) and ok

        from campus_planner.about_dialogs import AboutDialog
        about = AboutDialog(window)
        about.show()
        app.processEvents()
        about_out = Path.cwd() / "selftest_about.png"
        ok = about.grab().save(str(about_out)) and ok
        about.close()

        assets = ("github_avatar.png", "github_logo.png", "app_256.png")
        assets_ok = all(Path(theme.asset_path(name)).exists() for name in assets)
        print(f"SELFTEST {'OK' if ok and assets_ok else 'FAIL'} "
              f"assets={'OK' if assets_ok else 'MISSING'} {out}")
        return 0 if (ok and assets_ok) else 1

    # 启动动画：LOGO + 开发者头像 + 版本号 + 激励文案，结束后淡出再显示主窗口。
    from campus_planner.splash import SplashScreen
    splash = SplashScreen(3000)
    splash.finished.connect(window.show)
    splash.show_centered()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
