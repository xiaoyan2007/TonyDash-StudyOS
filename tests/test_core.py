"""核心逻辑单元测试：py -m unittest discover -s tests -v"""

import contextlib
import shutil
import sys
import unittest
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from campus_planner import core  # noqa: E402

TMP_ROOT = Path(__file__).resolve().parent / "_tmp"
TMP_ROOT.mkdir(exist_ok=True)


@contextlib.contextmanager
def temp_dir():
    # 不用 tempfile.TemporaryDirectory：它会 chmod 0700，在受限沙箱里反而写不进去。
    d = TMP_ROOT / ("t" + uuid.uuid4().hex[:8])
    d.mkdir()
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


class TestWeeks(unittest.TestCase):
    def test_all(self):
        self.assertEqual(len(core.expand_weeks(core.WeekSpec("all"), 18)), 18)

    def test_odd_even(self):
        self.assertEqual(sorted(core.expand_weeks(core.WeekSpec("odd"), 10)), [1, 3, 5, 7, 9])
        self.assertEqual(sorted(core.expand_weeks(core.WeekSpec("even"), 10)), [2, 4, 6, 8, 10])

    def test_custom(self):
        self.assertEqual(sorted(core.expand_weeks(core.WeekSpec("custom", "1-3, 6、8"), 18)), [1, 2, 3, 6, 8])
        self.assertEqual(core.expand_weeks(core.WeekSpec("custom", "1~3"), 18), {1, 2, 3})
        self.assertEqual(core.expand_weeks(core.WeekSpec("custom", "20-22"), 18), set())

    def test_label(self):
        self.assertEqual(core.weeks_label(core.WeekSpec("all"), 18), "1-18 周")
        self.assertEqual(core.weeks_label(core.WeekSpec("odd"), 18), "单周")
        self.assertEqual(core.weeks_label(core.WeekSpec("custom", "1,2,3,5,7,8"), 18), "1-3,5,7-8 周")

    def test_compress(self):
        self.assertEqual(core.compress_ranges([1, 2, 3, 5, 7, 8]), "1-3,5,7-8")
        self.assertEqual(core.compress_ranges([]), "")


class TestDates(unittest.TestCase):
    def setUp(self):
        self.term = date(2026, 9, 7)  # Monday

    def test_date_of_week_day(self):
        self.assertEqual(core.date_of_week_day(self.term, 1, 1), date(2026, 9, 7))
        self.assertEqual(core.date_of_week_day(self.term, 3, 7), date(2026, 9, 27))
        self.assertEqual(core.date_of_week_day(self.term, 9, 1), date(2026, 11, 2))

    def test_current_week(self):
        self.assertEqual(core.current_week(self.term, 18, date(2026, 9, 7)), 1)
        self.assertEqual(core.current_week(self.term, 18, date(2026, 11, 2)), 9)
        self.assertEqual(core.current_week(self.term, 18, date(2026, 1, 1)), 1)
        self.assertEqual(core.current_week(self.term, 18, date(2028, 1, 1)), 18)

    def test_term_name(self):
        self.assertEqual(core.default_term_name(date(2026, 10, 1)), "2026-2027学年第1学期")
        self.assertEqual(core.default_term_name(date(2027, 3, 1)), "2026-2027学年第2学期")
        self.assertEqual(core.default_term_name(date(2027, 1, 5)), "2026-2027学年第1学期")

    def test_blank_data_default_term(self):
        data = core.blank_data()
        self.assertEqual(data.settings.term_name, core.DEFAULT_TERM_NAME)
        self.assertEqual(data.settings.term_start, date(2026, 9, 14))
        self.assertEqual(data.settings.total_weeks, 18)
        self.assertEqual(len(data.periods), 12)
        self.assertEqual(data.periods[0].start, "08:05")
        self.assertEqual(data.periods[0].end, "08:50")


class TestConflicts(unittest.TestCase):
    def setUp(self):
        self.periods = [core.Period(a, b) for a, b in core.DEFAULT_PERIODS]

    def course(self, cid, day, start, end, weeks=None, name="课程"):
        return core.Course(cid, name, day=day, start=start, end=end,
                           weeks=weeks or core.WeekSpec())

    def test_overlap(self):
        a = self.course("a", 1, 1, 2)
        b = self.course("b", 1, 2, 3)
        c = self.course("c", 2, 1, 2)
        result = core.course_conflicts([a, b, c], a, 18)
        self.assertEqual([x[0].id for x in result], ["b"])

    def test_week_disjoint_no_conflict(self):
        a = self.course("a", 1, 1, 2, core.WeekSpec("odd"))
        b = self.course("b", 1, 1, 2, core.WeekSpec("even"))
        self.assertEqual(core.course_conflicts([a, b], a, 18), [])

    def test_partial_weeks(self):
        a = self.course("a", 1, 1, 2, core.WeekSpec("custom", "1-4"))
        b = self.course("b", 1, 1, 2, core.WeekSpec("custom", "3-6"))
        result = core.course_conflicts([a, b], a, 18)
        self.assertEqual(result[0][1], [3, 4])


class TestExams(unittest.TestCase):
    def exam(self, **kw):
        base = dict(id="e1", name="高数", date="2026-11-20", start_time="09:00",
                    duration=120, credits=5)
        base.update(kw)
        return core.Exam(**base)

    def test_status(self):
        e = self.exam()
        self.assertEqual(core.exam_status(e, datetime(2026, 11, 20, 8, 0)), "wait")
        self.assertEqual(core.exam_status(e, datetime(2026, 11, 20, 10, 0)), "live")
        self.assertEqual(core.exam_status(e, datetime(2026, 11, 20, 11, 1)), "done")

    def test_time_range(self):
        e = self.exam()
        self.assertEqual(e.time_range(), "09:00–11:00")
        self.assertEqual(core.exam_status(e, datetime(2026, 11, 20, 12, 0)), "done")

    def test_exam_conflict(self):
        a = self.exam()
        b = self.exam(id="e2", name="物理", start_time="10:30")
        c = self.exam(id="e3", name="英语", start_time="14:00")
        self.assertEqual([x.id for x in core.exam_conflicts([a, b, c], a)], ["e2"])

    def test_class_conflict(self):
        data = core.AppData()
        data.settings.term_start = date(2026, 9, 7)
        data.settings.total_weeks = 18
        data.periods = [core.Period(a, b) for a, b in core.DEFAULT_PERIODS]
        # 2026-11-20 是第 11 周周五
        data.courses = [core.Course("c1", "数据结构", day=5, start=1, end=2)]
        e = self.exam()
        self.assertEqual([c.id for c in core.exam_class_conflicts(e, data)], ["c1"])
        e2 = self.exam(date="2026-11-21")
        self.assertEqual(core.exam_class_conflicts(e2, data), [])


class TestNormalize(unittest.TestCase):
    def test_roundtrip(self):
        data = core.sample_data()
        again = core.AppData.from_dict(data.to_dict())
        self.assertEqual(len(again.courses), len(data.courses))
        self.assertEqual(len(again.exams), len(data.exams))
        self.assertEqual(again.settings.term_start, data.settings.term_start)

    def test_bad_values(self):
        raw = {
            "settings": {"term_start": "nope", "total_weeks": 99, "glass": -5},
            "periods": [{"start": "25:00", "end": "08:00"}],
            "courses": [
                {"name": "", "day": 99},
                {"name": "合法课", "day": 99, "start": 99, "end": -2, "color": 42},
            ],
            "exams": [
                {"name": "坏日期", "date": "2026-99-99"},
                {"name": "好考试", "date": "2026-11-20", "duration": 9999, "progress": 200},
            ],
            "exam_types": ["闭卷", "闭卷", ""],
        }
        data = core.AppData.from_dict(raw)
        self.assertEqual(len(data.courses), 1)
        self.assertEqual(data.courses[0].day, 7)
        self.assertLessEqual(data.courses[0].start, len(data.periods))
        self.assertEqual(len(data.exams), 1)
        self.assertEqual(data.exams[0].duration, 600)
        self.assertEqual(data.exams[0].progress, 100)
        self.assertEqual(data.settings.total_weeks, 30)
        self.assertGreaterEqual(data.settings.glass, 0)

    def test_old_data_gets_onboarding_defaults(self):
        data = core.AppData.from_dict({"courses": [], "settings": {"total_weeks": 18}})
        self.assertFalse(data.settings.onboarded)
        self.assertFalse(data.settings.checklist_dismissed)
        self.assertEqual(data.settings.hints_dismissed, [])

    def test_onboarding_flags_roundtrip(self):
        data = core.sample_data()
        data.settings.onboarded = True
        data.settings.checklist_dismissed = True
        data.settings.hints_dismissed = ["schedule", "todo"]
        again = core.AppData.from_dict(data.to_dict())
        self.assertTrue(again.settings.onboarded)
        self.assertTrue(again.settings.checklist_dismissed)
        self.assertEqual(again.settings.hints_dismissed, ["schedule", "todo"])

    def test_missing_settings(self):
        data = core.AppData.from_dict({"courses": []})
        self.assertEqual(data.settings.total_weeks, 18)
        self.assertGreaterEqual(len(data.periods), 2)
        self.assertIn("闭卷", data.exam_types)


class TestStorage(unittest.TestCase):
    def test_save_load(self):
        data = core.sample_data()
        with temp_dir() as tmp:
            path = Path(tmp) / "nested" / "data.json"
            core.save_data(data, path)
            self.assertTrue(path.exists())
            loaded = core.load_data(path)
            self.assertEqual(len(loaded.courses), len(data.courses))
            self.assertEqual(loaded.courses[0].name, data.courses[0].name)

    def test_corrupt_falls_back_to_blank(self):
        with temp_dir() as tmp:
            path = Path(tmp) / "data.json"
            path.write_text("{broken", encoding="utf-8")
            loaded = core.load_data(path)
            self.assertFalse(loaded.courses)
            self.assertFalse(loaded.exams)
            self.assertFalse(loaded.tasks)
            self.assertEqual(len(loaded.periods), 12)
            self.assertTrue(Path(str(path) + ".bad").exists())

    def test_missing_file_starts_blank(self):
        with temp_dir() as tmp:
            path = Path(tmp) / "nope.json"
            loaded = core.load_data(path)
            self.assertFalse(loaded.courses)
            self.assertFalse(loaded.exams)
            self.assertFalse(loaded.tasks)

    def test_import_rejects_other_json(self):
        with temp_dir() as tmp:
            path = Path(tmp) / "x.json"
            path.write_text('{"hello": 1}', encoding="utf-8")
            with self.assertRaises(ValueError):
                core.import_data(path)


class TestICS(unittest.TestCase):
    def test_build(self):
        data = core.sample_data()
        text = core.build_ics(data)
        self.assertIn("BEGIN:VCALENDAR", text)
        self.assertIn("END:VCALENDAR", text)
        self.assertIn("BEGIN:VEVENT", text)
        self.assertIn("SUMMARY:", text)
        self.assertTrue(text.endswith("\r\n"))
        self.assertEqual(text.count("BEGIN:VEVENT"), 8 * 18 + 9 + 12 + 5)  # 8 门全周 + 概率论单周 9 次 + 电路实验 12 次 + 5 场考试
        for line in text.split("\r\n"):
            self.assertLessEqual(len(line), 75, repr(line))

    def test_folding_respects_utf8_bytes(self):
        data = core.sample_data()
        data.courses[0].name = "跨学科工程实践与创新创业专题研讨课程" * 4
        text = core.build_ics(data)
        for line in text.split("\r\n"):
            self.assertLessEqual(len(line.encode("utf-8")), 75, repr(line))

    def test_escape(self):
        text = core._ics_escape("a,b;c\nd\\e")
        self.assertEqual(text, "a\\,b\\;c\\nd\\\\e")

    def test_export(self):
        data = core.sample_data()
        with temp_dir() as tmp:
            path = Path(tmp) / "x.ics"
            core.export_ics(data, path)
            self.assertIn("VCALENDAR", path.read_text(encoding="utf-8"))


class TestPeriods(unittest.TestCase):
    def test_redistribute(self):
        periods = [core.Period(a, b) for a, b in core.DEFAULT_PERIODS]
        new = core.redistribute_periods(periods, 45, 10)
        self.assertEqual(new[0].start, periods[0].start)
        self.assertEqual(core.period_duration(new[0]), 45)
        self.assertEqual(new[1].start, core.minutes_to_time(core.time_to_minutes(new[0].start) + 55))

    def test_norm_time(self):
        self.assertEqual(core.norm_hhmm("8:5"), "08:05")
        self.assertEqual(core.norm_hhmm("23:59"), "23:59")
        self.assertEqual(core.norm_hhmm("24:00", "07:00"), "07:00")


class TestEdges(unittest.TestCase):
    """审查中补的边界回归：空数据、坏数据、越界节次、自冲突。"""

    def test_course_conflicts_ignores_self(self):
        a = core.Course("a", "课程A", day=1, start=1, end=2,
                        weeks=core.WeekSpec())
        self.assertEqual(core.course_conflicts([a], a, 18), [])

    def test_weekspec_legacy_list_becomes_custom(self):
        spec = core.WeekSpec.from_dict([1, 2, 3])
        self.assertEqual(spec.mode, "custom")
        self.assertEqual(core.expand_weeks(spec, 18), {1, 2, 3})

    def test_weekspec_bad_mode_keeps_text(self):
        spec = core.WeekSpec.from_dict({"mode": "???", "text": "1-4"})
        self.assertEqual(spec.mode, "custom")
        self.assertEqual(core.expand_weeks(spec, 18), {1, 2, 3, 4})

    def test_weekspec_bad_mode_without_text_is_all(self):
        spec = core.WeekSpec.from_dict({"mode": "???", "text": ""})
        self.assertEqual(spec.mode, "all")
        self.assertEqual(len(core.expand_weeks(spec, 18)), 18)

    def test_from_dict_drops_incomplete_items(self):
        data = core.AppData.from_dict({
            "courses": [{"id": "a"}, {"name": "  "}, {"name": "好课"}],
            "exams": [{"name": "没有日期"}, {"name": "有日期", "date": "2026-12-01"}],
            "tasks": [{"id": "t"}, {"text": "有效"}, {"text": "  "}],
        })
        self.assertEqual([c.name for c in data.courses], ["好课"])
        self.assertEqual([e.name for e in data.exams], ["有日期"])
        self.assertEqual([t.text for t in data.tasks], ["有效"])

    def test_current_week_clamps_to_total(self):
        start = date(2026, 9, 14)
        self.assertEqual(core.current_week(start, 18, date(2027, 6, 1)), 18)
        self.assertEqual(core.current_week(start, 18, date(2028, 12, 31)), 18)
        # total 非法时回落 18 周，周次仍然按日期算
        self.assertEqual(core.current_week(start, 0, date(2026, 9, 21)), 2)
        self.assertEqual(core.current_week(start, 99, date(2026, 9, 21)), 2)

    def test_ics_skips_out_of_range_periods(self):
        data = core.blank_data()
        data.courses.append(core.Course("c1", "越界课程", day=1, start=99, end=100,
                                        weeks=core.WeekSpec()))
        text = core.build_ics(data)
        self.assertNotIn("越界课程", text)
        self.assertIn("BEGIN:VCALENDAR", text)
        self.assertIn("END:VCALENDAR", text)

    def test_ics_every_physical_line_within_75_bytes(self):
        data = core.sample_data()
        data.courses[0].name = "很长很长的课程名称用来触发折行" * 6
        data.courses[0].note = "备注 " * 40
        text = core.build_ics(data)
        for line in text.split("\r\n"):
            self.assertLessEqual(len(line.encode("utf-8")), 75, repr(line))
        self.assertTrue(text.endswith("\r\n"))


if __name__ == "__main__":
    unittest.main()
