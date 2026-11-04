import sys
sys.path.insert(0, '.')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QPixmap, QPainter, QColor
from PySide6.QtCore import Qt, QRectF
from campus_planner import theme

app = QApplication(sys.argv)
theme.load_fonts()
f = theme.icon_font(64)
f.setPointSizeF(48)
cands = [('E94C', 'Moon'), ('E94D', 'Sun'), ('E8B3', 'WeatherMoon'),
         ('E8B4', 'WeatherSunny'), ('E94E', '?'), ('E82E', '?'),
         ('E7C6', '?'), ('E9CE', '?'), ('E980', '?'), ('E8A3', '?'),
         ('E954', '?'), ('E955', '?'), ('E956', '?'), ('E957', '?'),
         ('E958', '?'), ('E959', '?')]


def render(ch):
    pm = QPixmap(64, 64)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setFont(f)
    p.setPen(QColor(255, 0, 0))
    p.drawText(QRectF(0, 0, 64, 64), Qt.AlignmentFlag.AlignCenter, chr(ch))
    p.end()
    return pm


ref = render(1)


def alpha(pm, x, y):
    return pm.toImage().pixelColor(x, y).alpha()


def count(pm):
    n = 0
    for y in range(0, 64, 2):
        for x in range(0, 64, 2):
            if alpha(pm, x, y) > 0:
                n += 1
    return n


print('ref count', count(ref))
for hexv, name in cands:
    ch = int(hexv, 16)
    pm = render(ch)
    same = pm.toImage() == ref.toImage()
    print(hexv, name, 'NOTDEF' if same else 'OK px~%d' % count(pm))
