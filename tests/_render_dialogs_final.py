"""version-finished 第一步：核对关于 / 更新日志弹窗渲染结果（不依赖看图）。"""
import os
import sys
from collections import Counter

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("APPDATA", "tests/_appdata_final3")
sys.path.insert(0, ".")

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from campus_planner import theme  # noqa: E402

app = QApplication([])
theme.load_fonts()
app.setFont(theme.font(13))
app.setStyleSheet(theme.global_qss())

from campus_planner.about_dialogs import AboutDialog, ChangelogDialog  # noqa: E402


def stats(name, dlg):
    dlg.show()
    app.processEvents()
    pm = dlg.grab()
    pm.save(f"tests/_shots/{name}_final.png")
    from PIL import Image

    im = Image.open(f"tests/_shots/{name}_final.png").convert("RGB")
    w, h = im.size
    cnt = Counter(im.getdata())
    top = [(f"#{r:02X}{g:02X}{b:02X}", n) for (r, g, b), n in cnt.most_common(5)]
    kids = [k for k in dlg.findChildren(QWidget)
            if k.isVisible() and k.sizeHint().height() > 0]
    ext = (max((k.y() + k.height()) for k in kids),) if kids else ()
    print(f"{name}: {w}x{h}  hint={dlg.sizeHint().height()}  "
          f"contentBottom={ext[0] if ext else '-'}  "
          f"topColors={top[:3]}")
    dlg.close()
    app.processEvents()


stats("about", AboutDialog(None))
stats("changelog", ChangelogDialog(None))

# 深色模式再核一遍
theme.set_theme("dark")
app.setStyleSheet(theme.global_qss())
stats("about_dark", AboutDialog(None))
stats("changelog_dark", ChangelogDialog(None))

print("DONE")
