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

theme.load_fonts()
theme.apply_global_qss(force=True)

out = ROOT / "tests" / "_shots" / "popup"
out.mkdir(parents=True, exist_ok=True)

for mode in ("light", "dark"):
    theme.set_theme(mode)
    theme.apply_global_qss(force=True)
    tp = widgets.TimePicker()
    tp.set_time("08:05")
    tp.show()
    app.processEvents()
    tp.hour._open_popup()
    app.processEvents()
    pop = tp.hour._popup
    print(mode, "popup", pop.width(), pop.height(), "list", pop.list.width(),
          "rows", pop.list.count(), "cur", pop.list.currentRow())
    pop.grab().save(str(out / f"{mode}_popup.png"))
    pop.close()
    tp.close()
print("done")
