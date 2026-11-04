"""待办数据模型、跨天重置与更新日志文本的单元测试。"""
from __future__ import annotations

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from campus_planner import changelog, core  # noqa: E402


class TaskModelTest(unittest.TestCase):
    def test_roundtrip_and_legacy_data(self):
        task = core.Task("t1", "背单词", "daily", done=True,
                         done_date="2026-11-01", deadline="2026-11-09",
                         history={"2026-11-01": "2026-11-01T08:00:00"})
        data = core.AppData.from_dict({
            "version": 2, "settings": {}, "periods": [],
            "courses": [], "exams": [], "tasks": [task.to_dict()],
        })
        self.assertEqual(len(data.tasks), 1)
        self.assertEqual(data.tasks[0].text, "背单词")
        self.assertTrue(data.tasks[0].done)
        self.assertEqual(data.tasks[0].history["2026-11-01"], "2026-11-01T08:00:00")
        legacy = core.AppData.from_dict({"version": 1, "settings": {}, "periods": [],
                                         "courses": [], "exams": []})
        self.assertEqual(legacy.tasks, [])

    def test_rollover_daily_weekly_once(self):
        today = date(2026, 11, 2)
        daily = core.Task("d", "每日", "daily", done=True, done_date="2026-11-01")
        weekly = core.Task("w", "每周", "weekly", done=True, done_date="2026-10-25")
        fresh = core.Task("f", "今天完成", "once", done=True, done_date="2026-11-02")
        old = core.Task("o", "昨天完成", "once", done=True, done_date="2026-11-01")
        tasks = [daily, weekly, fresh, old]
        self.assertTrue(core.rollover_tasks(tasks, today))
        self.assertFalse(daily.done)
        self.assertFalse(weekly.done)
        self.assertEqual([t.id for t in tasks], ["d", "w", "f"])
        self.assertFalse(core.rollover_tasks(tasks, today))

    def test_stats_and_due_state(self):
        today = date(2026, 11, 2)
        tasks = [core.Task("a", "A", "once", done=True),
                 core.Task("b", "B", "once"),
                 core.Task("c", "C", "daily")]
        self.assertEqual(core.task_stats(tasks), (3, 1, 2))
        self.assertEqual(core.task_due_state(
            core.Task("x", "X", "once", deadline="2026-11-01"), today), "overdue")
        self.assertEqual(core.task_due_state(
            core.Task("y", "Y", "once", deadline="2026-11-02"), today), "today")
        self.assertEqual(core.task_due_state(
            core.Task("z", "Z", "once", deadline="2026-11-05"), today), "soon")
        self.assertIsNone(core.task_due_state(core.Task("d", "D", "daily"), today))

    def test_sorted_daily_before_once(self):
        tasks = [core.Task("o", "一次性", "once", deadline="2026-11-01"),
                 core.Task("w", "每周", "weekly"),
                 core.Task("d", "每日", "daily")]
        self.assertEqual([t.id for t in core.sorted_tasks(tasks)], ["d", "w", "o"])


class ChangelogTest(unittest.TestCase):
    def test_all_versions_present(self):
        html = changelog.changelog_html()
        self.assertIn("Beta 1.3", html)
        self.assertIn("Beta 1.2", html)
        self.assertIn("Beta 1.1", html)
        self.assertIn("Beta 1.0", html)
        self.assertEqual(changelog.latest().version, core.APP_VERSION)
        self.assertIn(core.APP_NAME, html)
        self.assertNotIn("✨", html)
        self.assertIn('<p class="tagline">', html)

    def test_plain_text_has_sections(self):
        rel = changelog.release_by_version("Beta 1.0")
        text = changelog.release_plain_text(rel)
        self.assertIn("Beta 1.0", text)
        self.assertIn("【新增】", text)
        self.assertNotIn("<b>", text)
        self.assertTrue(text.startswith("课表 · 期末 Beta 1.0"), text.splitlines()[0])


if __name__ == "__main__":
    unittest.main()
