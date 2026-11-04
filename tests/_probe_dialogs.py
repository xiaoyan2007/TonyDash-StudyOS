# -*- coding: utf-8 -*-
"""检查各弹窗是否有控件被压扁（高度小于 minimumSizeHint）导致文字被裁切。"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

app = QApplication(sys.argv)
from campus_planner import core, theme, widgets  # noqa: E402
from campus_planner import about_dialogs, dialogs  # noqa: E402

theme.load_fonts()
theme.apply_global_qss(force=True)


def check(name, dlg):
    dlg.show()
    for _ in range(6):
        app.processEvents()
    bad = []
    for w in dlg.findChildren(QWidget):
        if not w.isVisible() or w.width() <= 1 or w.height() <= 1:
            continue
        hint = w.minimumSizeHint()
        if hint.height() > w.height() + 1 or hint.width() > w.width() + 1:
            bad.append((type(w).__name__, w.objectName(), w.width(), w.height(),
                        hint.width(), hint.height()))
    print(f"[{name}] size={dlg.width()}x{dlg.height()} 挤压控件={len(bad)}")
    for b in bad[:8]:
        print("   ", b)
    dlg.close()


for mode in ("light", "dark"):
    theme.set_theme(mode)
    theme.apply_global_qss(force=True)
    print("=== mode:", mode)
    check("About", about_dialogs.AboutDialog())
    check("Changelog", about_dialogs.ChangelogDialog())
    task = core.Task(id="t1", text="背 30 个六级单词", type="daily", done=True,
                     created="2026-11-01", done_date="2026-11-04",
                     deadline="2026-11-10",
                     history={f"2026-11-{d:02d}": "完成" for d in range(1, 7)})
    check("TaskHistory", about_dialogs.TaskHistoryDialog(None, task))
print("done")
