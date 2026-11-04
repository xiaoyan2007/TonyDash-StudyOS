"""离屏渲染主窗口三个页面，便于目检 UI。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["APPDATA"] = str(ROOT / "tests" / "_appdata")
(ROOT / "tests" / "_shots").mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from campus_planner import theme  # noqa: E402


def main():
    app = QApplication(sys.argv)
    theme.load_fonts()
    app.setFont(theme.font(13))
    theme.apply_global_qss(force=True)
    from campus_planner.main import MainWindow

    win = MainWindow()
    win.resize(1240, 800)
    win.show()
    app.processEvents()
    for i, name in enumerate(("schedule", "exams", "settings")):
        win.go(i)
        app.processEvents()
        path = ROOT / "tests" / "_shots" / f"page_{name}.png"
        win.grab().save(str(path))
        print("saved", path)

    st = win.settings_page
    bar = st.scroll.verticalScrollBar()
    bar.setValue(bar.maximum())
    app.processEvents()
    win.grab().save(str(ROOT / "tests" / "_shots" / "page_settings_bottom.png"))
    print("saved settings bottom")

    win.resize(390, 844)
    win.go(0)
    app.processEvents()
    win.grab().save(str(ROOT / "tests" / "_shots" / "page_narrow.png"))
    print("saved narrow")


if __name__ == "__main__":
    main()
