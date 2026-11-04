"""诊断：找出让 QCalendarWidget 变黑的 QSS 规则。"""
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
theme.set_theme("light")
full = theme.global_qss()

# 拆成规则块
blocks = []
for chunk in full.split("}"):
    chunk = chunk.strip()
    if not chunk:
        continue
    blocks.append(chunk + "}")


def build(host):
    w = QWidget()
    w.resize(340, 300)
    lay = QVBoxLayout(w)
    cal = QCalendarWidget(w)
    cal.setSelectedDate(QDate(2026, 9, 14))
    lay.addWidget(cal)
    w.show()
    return w


def dominant(w):
    img = w.grab().toImage()
    counts = {}
    for y in range(0, img.height(), 3):
        for x in range(0, img.width(), 3):
            c = img.pixelColor(x, y)
            k = (c.red(), c.green(), c.blue())
            counts[k] = counts.get(k, 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])[:2]


print("== full qss ==", dominant(build(1)))

# 逐块单独应用
for blk in blocks:
    app.setStyleSheet(blk)
    w = build(1)
    top = dominant(w)
    if top and top[0][0][0] < 60:
        print("BLACK WITH:", blk.replace("\n", " ")[:160])
    w.deleteLater()

app.setStyleSheet(full)
print("== full again ==", dominant(build(1)))
