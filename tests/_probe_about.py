# -*- coding: utf-8 -*-
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
from campus_planner import theme, widgets  # noqa: E402
from campus_planner.about_dialogs import AboutDialog  # noqa: E402

theme.load_fonts()
theme.apply_global_qss(force=True)

scr = app.primaryScreen()
print("screen", scr.availableGeometry())

dlg = AboutDialog()
dlg.show()
app.processEvents()
print("dlg size        ", dlg.width(), dlg.height())
print("dlg sizeHint    ", dlg.sizeHint().width(), dlg.sizeHint().height())
print("dlg minimumHint ", dlg.minimumSizeHint().width(), dlg.minimumSizeHint().height())
print("body hint       ", dlg.body.sizeHint().height())
print("body hint       2", dlg.body_layout.sizeHint().height())
print("body minimum    ", dlg.body_layout.minimumSize().height())

cards = dlg.findChildren(widgets.GlassCard)
for c in cards:
    lay = c.layout()
    print("card", c.objectName(), "geom", c.width(), c.height(),
          "hint", c.sizeHint().height(), "minhint", c.minimumSizeHint().height(),
          "laymin", lay.minimumSize().height() if lay else None)
