"""诊断：QCalendarWidget 背景在样式表下的实际着色。"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("APPDATA", str(ROOT / "tests" / "_appdata_cal"))

from PySide6.QtCore import QDate  # noqa: E402
from PySide6.QtWidgets import QApplication, QCalendarWidget, QVBoxLayout, QWidget  # noqa: E402

from campus_planner import theme  # noqa: E402

app = QApplication(sys.argv)
theme.load_fonts()


def build():
    w = QWidget()
    w.resize(340, 300)
    lay = QVBoxLayout(w)
    cal = QCalendarWidget(w)
    cal.setSelectedDate(QDate(2026, 9, 14))
    lay.addWidget(cal)
    w.show()
    return w


def top_colors(w, n=4):
    img = w.grab().toImage()
    counts = {}
    for y in range(0, img.height(), 3):
        for x in range(0, img.width(), 3):
            c = img.pixelColor(x, y)
            k = (c.red(), c.green(), c.blue(), c.alpha())
            counts[k] = counts.get(k, 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])[:n]


CASES = {
    "none": "",
    "solid red on QCalendarWidget QWidget": "QCalendarWidget QWidget { background: #FF0000; }",
    "solid white on QCalendarWidget QWidget": "QCalendarWidget QWidget { background: #FFFFFF; }",
    "rgba white 250": "QCalendarWidget QWidget { background: rgba(255,255,255,250); }",
    "rgba white 255": "QCalendarWidget QWidget { background: rgba(255,255,255,255); }",
    "white on QCalendarWidget": "QCalendarWidget { background: #FFFFFF; }",
    "white on QTableView": "QTableView { background: #FFFFFF; }",
    "white on QAbstractItemView": "QAbstractItemView { background: #FFFFFF; }",
    "QCalendarWidget + QTableView white": (
        "QCalendarWidget { background: #FFFFFF; }"
        "QCalendarWidget QTableView { background: #FFFFFF; }"
    ),
}

for name, qss in CASES.items():
    app.setStyleSheet(qss)
    w = build()
    print(f"{name:42s} -> {top_colors(w)}")
    w.close()
    w.deleteLater()
    app.processEvents()
