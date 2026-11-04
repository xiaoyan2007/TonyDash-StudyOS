"""诊断：日历弹层为什么是黑的。离屏渲染裸 QCalendarWidget 与 CalendarPopup。"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("APPDATA", str(ROOT / "tests" / "_appdata_cal"))

from PySide6.QtCore import QDate, Qt  # noqa: E402
from PySide6.QtGui import QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication, QCalendarWidget, QWidget, QVBoxLayout  # noqa: E402

from campus_planner import theme, widgets  # noqa: E402

OUT = ROOT / "tests" / "_shots" / "cal"
OUT.mkdir(parents=True, exist_ok=True)


def save(w, name):
    w.grab().save(str(OUT / name))
    print("saved", name, w.width(), w.height())


def analyse(path):
    from PIL import Image

    im = Image.open(path).convert("RGBA")
    px = im.load()
    counts = {}
    for y in range(0, im.height, 2):
        for x in range(0, im.width, 2):
            c = px[x, y]
            counts[c] = counts.get(c, 0) + 1
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:3]
    print("  ", path.name, "top:", [(t[0], t[1]) for t in top])


app = QApplication(sys.argv)
theme.load_fonts()
theme.set_theme("light")
theme.apply_global_qss()

# 1. 裸 QCalendarWidget，带全局样式表
host = QWidget()
host.resize(340, 300)
lay = QVBoxLayout(host)
cal = QCalendarWidget(host)
cal.setSelectedDate(QDate(2026, 9, 14))
lay.addWidget(cal)
host.show()
save(host, "bare_global_qss.png")

# 2. 裸 QCalendarWidget，不带全局样式表
app.setStyleSheet("")
host2 = QWidget()
host2.resize(340, 300)
lay2 = QVBoxLayout(host2)
cal2 = QCalendarWidget(host2)
cal2.setSelectedDate(QDate(2026, 9, 14))
lay2.addWidget(cal2)
host2.show()
save(host2, "bare_no_qss.png")

# 3. 项目的 CalendarPopup（浅色）
theme.apply_global_qss()
pop = widgets.CalendarPopup()
pop.cal.setSelectedDate(QDate(2026, 9, 14))
pop.adjustSize()
pop.show()
save(pop, "calendar_popup_light.png")

theme.set_theme("dark")
theme.apply_global_qss()
pop2 = widgets.CalendarPopup()
pop2.cal.setSelectedDate(QDate(2026, 9, 14))
pop2.adjustSize()
pop2.show()
save(pop2, "calendar_popup_dark.png")

for f in sorted(OUT.glob("*.png")):
    analyse(f)

print("card_rgba(250) =", theme.card_rgba(250))
print("POPUP light =", theme.LIGHT.get("popup"), "dark =", theme.DARK.get("popup"))
