"""version-finished 第二步：边界与健壮性快速体检（先找问题，再写回归测试）。"""
import os
import sys
import time
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("APPDATA", "tests/_appdata_review")
sys.path.insert(0, ".")

from campus_planner import core  # noqa: E402

FAILS = []


def check(name, fn):
    try:
        fn()
        print(f"  ok   {name}")
    except Exception as exc:  # noqa: BLE001
        FAILS.append(f"{name}: {type(exc).__name__}: {exc}")
        print(f"  FAIL {name}: {type(exc).__name__}: {exc}")


print("== 数据层健壮性 ==")


def corrupt_json():
    core.data_path().parent.mkdir(parents=True, exist_ok=True)
    core.data_path().write_text("{ not json ", encoding="utf-8")
    d = core.load_data()
    if d.courses or d.exams or d.tasks:
        raise AssertionError("损坏 JSON 应回落空数据")
    if core.data_path().exists() and core.data_path().read_text(encoding="utf-8") == "{ not json ":
        raise AssertionError("损坏文件应被改名保留")


check("损坏 JSON 回落空数据", corrupt_json)


def missing_fields():
    raw = {"version": 1, "courses": [], "settings": {"total_weeks": "x",
             "term_name": None, "theme_mode": 5}}
    d = core.AppData.from_dict(raw)
    if d.settings.total_weeks != 18:
        raise AssertionError(f"total_weeks 应回落默认，实际 {d.settings.total_weeks}")
    if not d.settings.term_name:
        raise AssertionError("term_name 应回落默认")
    if d.settings.theme_mode not in ("light", "dark"):
        raise AssertionError("theme_mode 非法值应回落 light")
    if d.periods and len(d.periods) != 12:
        raise AssertionError("缺 periods 应回落默认 12 节")


check("from_dict 缺字段/错类型容错", missing_fields)


def v1_migration():
    raw = {"courses": [{"id": "c", "name": "x", "day": 1, "start": 1, "end": 2,
                        "weeks": [1, 2, 3]}], "settings": {"term_start": "2026-09-14"}}
    d = core.AppData.from_dict(raw)
    if d.settings.term_start != date(2026, 9, 14):
        raise AssertionError(f"term_start 迁移错误: {d.settings.term_start}")
    if len(d.courses) != 1 or d.courses[0].weeks.mode != "custom":
        raise AssertionError("旧版周次数组未迁移成 custom")


check("旧版缺字段数据迁移", v1_migration)


def bad_course_dropped():
    d = core.AppData.from_dict({"courses": [{"id": "a"}, {"name": ""}],
                                "exams": [{"name": "无日期考试"}]})
    if d.courses or d.exams:
        raise AssertionError("缺名字的课程/考试应被丢弃而不是抛错")


check("缺关键字段的条目被安全丢弃", bad_course_dropped)


def json_roundtrip():
    d = core.sample_data()
    txt = d.to_dict()
    again = core.AppData.from_dict(txt)
    if again.settings.term_name != d.settings.term_name:
        raise AssertionError("往返丢失字段")
    if len(again.tasks) != len(d.tasks):
        raise AssertionError("往返丢失待办")
    if again.settings.theme_mode != d.settings.theme_mode:
        raise AssertionError("往返丢失主题")


check("to_dict/from_dict 往返", json_roundtrip)


print("== 日期与周次边界 ==")


def current_week_bounds():
    start = date(2026, 9, 14)
    if core.current_week(start, 18, date(2026, 9, 13)) != 1:
        raise AssertionError("开学前一天应为第 1 周")
    if core.current_week(start, 18, date(2026, 9, 14)) != 1:
        raise AssertionError("开学当天应为第 1 周")
    if core.current_week(start, 18, date(2026, 9, 20)) != 1:
        raise AssertionError("第一周周日应为第 1 周")
    if core.current_week(start, 18, date(2026, 9, 21)) != 2:
        raise AssertionError("第二周周一应为第 2 周")
    if core.current_week(start, 18, date(2027, 3, 20)) != 18:
        raise AssertionError("学期末应 clamp 到第 18 周")
    if core.current_week(start, 18, date(2028, 12, 31)) != 18:
        raise AssertionError("远未来应 clamp")
    if core.current_week(start, 0, date(2026, 9, 21)) != 2:
        raise AssertionError("total=0 应回落 18 周，周次仍为 2")
    if core.current_week(start, 30, date(2026, 9, 14)) != 1:
        raise AssertionError("总周数 30 时开学当天应为第 1 周")


check("current_week 边界", current_week_bounds)


def date_of_week_day():
    d = core.date_of_week_day(date(2026, 9, 14), 1, 1)
    if d != date(2026, 9, 14):
        raise AssertionError(f"第 1 周周一应为开学日，实际 {d}")
    d2 = core.date_of_week_day(date(2026, 9, 14), 30, 1)
    if d2 != date(2027, 4, 5):
        raise AssertionError(f"第 30 周周一应为 2027-04-05，实际 {d2}")
    d3 = core.date_of_week_day(date(2026, 12, 28), 4, 7)
    if d3.month != 1:
        raise AssertionError(f"跨年周日计算错误: {d3}")


check("date_of_week_day 边界与跨年", date_of_week_day)


def rollover():
    t = core.Task(id="t1", text="每日", type="daily", done=True,
                  created="2026-11-03", done_date="2026-11-03")
    tasks = [t]
    if core.rollover_tasks(tasks, date(2026, 11, 5)) is not True:
        raise AssertionError("隔天应触发 rollover")
    if t.done or t.done_date:
        raise AssertionError("隔天后应重置为未完成")
    bad = core.Task(id="t2", text="一次性", type="once", done=True,
                    created="2026-11-01", done_date="2026-11-01")
    tasks2 = [bad]
    core.rollover_tasks(tasks2, date(2026, 11, 5))
    if tasks2:
        raise AssertionError("过期一次性任务应移除")
    weekly = core.Task(id="t3", text="每周", type="weekly", done=True,
                       created="2026-11-01", done_date="2026-10-30")
    tasks3 = [weekly]
    core.rollover_tasks(tasks3, date(2026, 11, 5))
    if weekly.done:
        raise AssertionError("上一周完成的每周待办应重置")


check("rollover_tasks 边界", rollover)


print("== 课表 / 考试 ==")


def conflict_detection():
    periods = core.default_periods()
    c1 = core.Course("a", "课程A", day=1, start=1, end=2, weeks=core.WeekSpec())
    c2 = core.Course("b", "课程B", day=1, start=1, end=2, weeks=core.WeekSpec())
    c3 = core.Course("c", "课程C", day=2, start=1, end=2, weeks=core.WeekSpec())
    c4 = core.Course("d", "课程D", day=1, start=3, end=4, weeks=core.WeekSpec())
    if core.course_conflicts([c1, c2, c3, c4], c1, 18):
        raise AssertionError("同节次应判定冲突")
    if core.course_conflicts([c1, c3], c1, 18):
        raise AssertionError("不同天不应冲突")
    if core.course_conflicts([c1], c1, 18):
        raise AssertionError("自己不应与自己冲突")
    if core.course_conflicts([c1, c4], c1, 18):
        raise AssertionError("节次不重叠不应冲突")


check("course_conflicts 边界", conflict_detection)


def week_overlap_conflict():
    c1 = core.Course("a", "A", day=1, start=1, end=1, weeks=core.WeekSpec(mode="odd"))
    c2 = core.Course("b", "B", day=1, start=1, end=1, weeks=core.WeekSpec(mode="even"))
    if core.course_conflicts([c1, c2], c1, 18):
        raise AssertionError("单双周互不重叠不应冲突")
    c3 = core.Course("c", "C", day=1, start=1, end=1, weeks=core.WeekSpec(mode="odd"))
    if not core.course_conflicts([c1, c3], c1, 18):
        raise AssertionError("同为单周应冲突")


check("单双周周次重叠冲突", week_overlap_conflict)


def redistribute():
    out = core.redistribute_periods(core.default_periods(), 45, 10)
    if len(out) != len(core.default_periods()):
        raise AssertionError("节次数变了")
    if out[0].start != "08:05":
        raise AssertionError(f"重排应从 08:05 起，实际 {out[0].start}")
    if out[0].end != "08:50":
        raise AssertionError("第一节时长应为 45 分钟")
    if core.redistribute_periods([], 45, 10) != []:
        raise AssertionError("空作息应返回空")


check("redistribute_periods 边界", redistribute)


print("== ICS ==")


def ics_special():
    d = core.blank_data()
    d.courses.append(core.Course("c1", "语文, 数学; 作业\n换行", day=1, start=1, end=1,
                                 weeks=core.WeekSpec()))
    txt = core.build_ics(d)
    summary = [ln for ln in txt.split("\r\n") if ln.startswith("SUMMARY:")][0]
    if "\," not in summary:
        raise AssertionError(f"逗号未转义: {summary!r}")
    if "\;" not in summary:
        raise AssertionError("分号未转义")
    if "\\n" not in summary:
        raise AssertionError("换行未转义")
    for line in txt.split("\r\n"):
        if len(line.encode("utf-8")) > 75:
            raise AssertionError(f"折行超 75 字节: {line!r}")


check("ICS 转义与折行", ics_special)


def ics_many_weeks():
    d = core.blank_data()
    d.courses.append(core.Course("c1", "长周课", day=1, start=1, end=1,
                                 weeks=core.WeekSpec(mode="all")))
    txt = core.build_ics(d)
    if txt.count("BEGIN:VEVENT") != 18:
        raise AssertionError(f"应 18 个事件，实际 {txt.count('BEGIN:VEVENT')}")


check("ICS 逐周事件数", ics_many_weeks)


def ics_bad_period():
    d = core.blank_data()
    d.courses.append(core.Course("c1", "越界课程", day=1, start=99, end=100,
                                 weeks=core.WeekSpec()))
    txt = core.build_ics(d)
    if "越界课程" in txt:
        raise AssertionError("节次越界应跳过而不是崩溃")


check("ICS 节次越界跳过", ics_bad_period)


print("== 性能 ==")


def big_list_speed():
    d = core.blank_data()
    for i in range(60):
        d.tasks.append(core.Task(id=f"t{i}", text=f"待办 {i}", type="daily"))
        d.courses.append(core.Course(f"c{i}", f"课程{i}", day=(i % 7) + 1,
                                     start=1, end=2, weeks=core.WeekSpec()))
    t0 = time.time()
    core.task_stats(d.tasks)
    core.conflicts_map(d.courses, d.settings.total_weeks)
    core.upcoming_exams(d.exams)
    core.sorted_tasks(d.tasks)
    dt = time.time() - t0
    if dt > 0.5:
        raise AssertionError(f"60 条数据计算过慢: {dt:.2f}s")


check("60 条数据计算性能", big_list_speed)


print("== 空数据全页 ==")


def empty_pages():
    from PySide6.QtWidgets import QApplication

    from campus_planner import theme

    from campus_planner.pages import exams, home, schedule, todo

    if QApplication.instance() is None:
        app = QApplication([])
        theme.load_fonts()
        app.setFont(theme.font(13))
        app.setStyleSheet(theme.global_qss())
    else:
        app = QApplication.instance()

    for cls, args in ((home.HomePage, ()), (schedule.SchedulePage, ()),
                      (exams.ExamPage, ()), (todo.TaskPage, ())):
        w = cls()
        if cls is schedule.SchedulePage:
            w.set_data(core.blank_data(), 1)
        else:
            w.set_data(core.blank_data())
        w.resize(1200, 800)
        w.show()
        app.processEvents()
        pm = w.grab()
        if pm.isNull():
            raise AssertionError(f"{cls.__name__} 空白态无法渲染")
        w.close()
        app.processEvents()


check("空数据四页渲染", empty_pages)


def split_bar_zero():
    from PySide6.QtWidgets import QApplication

    from campus_planner import theme
    from campus_planner.widgets import SplitProgressBar

    app = QApplication.instance() or QApplication([])
    theme.load_fonts()
    app.setFont(theme.font(13))
    app.setStyleSheet(theme.global_qss())
    bar = SplitProgressBar()
    bar.resize(300, 7)
    bar.show()
    app.processEvents()
    bar.set_ratio(0, 0)
    app.processEvents()
    pm = bar.grab()
    if pm.isNull():
        raise AssertionError("空白进度条无法渲染")
    # total=0 时进度应为 0，不能整条变红
    if bar.progress() != 0.0:
        raise AssertionError(f"total=0 时进度应为 0，实际 {bar.progress()}")
    bar.close()


check("SplitProgressBar total=0", split_bar_zero)


print()
if FAILS:
    print(f"==== {len(FAILS)} 项失败 ====")
    for f in FAILS:
        print("  " + f)
else:
    print("==== 全部通过 ====")
