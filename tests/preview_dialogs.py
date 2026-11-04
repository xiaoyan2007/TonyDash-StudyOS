"""弹窗离屏预览。"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from campus_planner import core, dialogs, theme  # noqa: E402


def main():
    app = QApplication([])
    theme.load_fonts()
    app.setFont(theme.app_font())
    app.setStyleSheet(theme.global_qss())
    data = core.sample_data()
    out = Path(__file__).resolve().parent / "_shots"
    out.mkdir(exist_ok=True)

    d1 = dialogs.CourseDialog(None, data, data.courses[0])
    d1.show()
    app.processEvents()
    d1.grab().save(str(out / "dialog_course.png"))
    print("course", d1.size())

    d2 = dialogs.ExamDialog(None, data, data.exams[0])
    d2.show()
    app.processEvents()
    d2.grab().save(str(out / "dialog_exam.png"))
    print("exam", d2.size())

    d3 = dialogs.CourseDialog(None, data, None, default_day=3, default_period=5)
    d3.show()
    app.processEvents()
    d3.grab().save(str(out / "dialog_course_new.png"))
    print("new", d3.size())


if __name__ == "__main__":
    main()
