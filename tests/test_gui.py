"""离屏 GUI 冒烟测试：主窗口、五个页面、两个弹窗与设置编辑。"""
from __future__ import annotations

import os
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
GUI_DATA = ROOT / "tests" / "_gui_appdata"
os.environ["APPDATA"] = str(GUI_DATA)
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QDate, QPoint, QTime  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QTextBrowser  # noqa: E402

from campus_planner import core, dialogs, theme  # noqa: E402


class GuiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        theme.load_fonts()
        cls.app.setFont(theme.font(13))
        theme.apply_global_qss(force=True)

    def setUp(self):
        shutil.rmtree(GUI_DATA, ignore_errors=True)
        GUI_DATA.mkdir(parents=True, exist_ok=True)
        from campus_planner.main import MainWindow

        self.win = MainWindow()
        self.win.resize(1240, 800)
        self.win.show()
        self.app.processEvents()
        # 旧测试依赖示例数据，这里显式注入（启动空白由 core 测试覆盖）
        self.win.data = core.sample_data()
        self.win.data.settings.onboarded = True
        self.win.week = core.current_week(
            self.win.data.settings.term_start, self.win.data.settings.total_weeks)
        core.save_data(self.win.data)
        self.win._refresh_pages()

    def tearDown(self):
        self.win.close()
        self.app.processEvents()

    def test_pages_render(self):
        for index in range(len(self.win._page_objs)):
            self.win.go(index)
            self.app.processEvents()
            pm = self.win.grab()
            self.assertFalse(pm.isNull())
            self.assertGreater(pm.width(), 900)
        # 「课表导入」(索引 4) 是课程表下的功能页，不在左栏；导航项 7 个
        self.assertEqual(len(self.win.nav_buttons), 7)
        self.assertNotIn("课表导入", [b.label for b in self.win.nav_buttons])
        self.assertEqual(self.win.nav_targets, [0, 1, 2, 3, 5, 6, 7])

    def test_week_navigation(self):
        self.win._on_week(3)
        self.assertEqual(self.win.week, 3)
        self.assertEqual(self.win.schedule_page.timetable.week, 3)

    def test_settings_shortcuts_after_nav_growth(self):
        """Beta 1.5 导航扩到 8 页后，Ctrl+5 与 Ctrl+, 仍应跳「设置」（索引 7）。

        回归场景：导航改版前设置是索引 4；改版后索引 4 变成了「课表导入」，
        快捷键若忘了跟着改，按 Ctrl+5 会跳错页。
        """
        from campus_planner.pages import settings as settings_page

        by_seq = {}
        for sc in self.win._shortcuts:
            key = sc.key().toString().lower().replace(" ", "")
            by_seq[key] = sc
        for seq in ("ctrl+5", "ctrl+,"):
            self.assertIn(seq, by_seq, f"缺少快捷键 {seq}")
            by_seq[seq].activated.emit()
            self.app.processEvents()
            self.assertEqual(self.win.stack.currentIndex(), 7, f"{seq} 没跳设置页")
            self.assertIsInstance(self.win._page_objs[7], settings_page.SettingsPage)
        self.assertEqual(self.win.nav_buttons[6].label, "设置")
        self.assertTrue(self.win.nav_buttons[6].isChecked())

    def test_arrow_keys_change_week_on_schedule_page(self):
        """课表页页头写着「← → 换周」，方向键就必须真的能在课表页换周。

        回归场景：导航扩页后 _key_week 只在主页生效，课表页按键没反应。
        """
        from PySide6.QtCore import Qt as CQt

        self.win.go(1)
        self.app.processEvents()
        before = self.win.week
        self.win._key_week(1)
        self.assertEqual(self.win.week, before + 1)
        # 课程表页按真实按键也能换周
        QTest.keyClick(self.win, CQt.Key.Key_Left)
        self.app.processEvents()
        self.assertEqual(self.win.week, before)
        # 词典查询页不应响应换周
        self.win.go(5)
        self.app.processEvents()
        kept = self.win.week
        self.win._key_week(1)
        self.assertEqual(self.win.week, kept)

    def test_ctrl_n_only_opens_dialogs_on_course_pages(self):
        """Ctrl+N 只在课表 / 待办 / 考试页触发了对应新建，其他页面不打扰。"""
        calls = []
        self.win.new_course = lambda *a: calls.append("course")
        self.win.new_exam = lambda: calls.append("exam")

        self.win.go(2)  # 待办页：走聚焦输入框分支，不会调 new_course
        self.app.processEvents()
        self.win._new_current()
        self.assertNotIn("course", calls)

        self.win.go(3)
        self.app.processEvents()
        self.win._new_current()
        self.assertEqual(calls, ["exam"])

        calls.clear()
        self.win.go(5)  # 词典查询页
        self.app.processEvents()
        self.win._new_current()
        self.win.go(6)  # 单词本页
        self.app.processEvents()
        self.win._new_current()
        self.win.go(7)  # 设置页
        self.app.processEvents()
        self.win._new_current()
        self.win.go(4)  # 课表导入页
        self.app.processEvents()
        self.win._new_current()
        self.assertEqual(calls, [], "词典 / 单词本 / 设置 / 导入页不该弹新建课程")

        self.win.go(1)  # 课程表页仍然能新建
        self.app.processEvents()
        self.win._new_current()
        self.assertEqual(calls, ["course"])

    def test_course_dialog_save(self):
        dlg = dialogs.CourseDialog(self.win, self.win.data, None, 2, 3)
        dlg.name.setText("离散数学")
        dlg.teacher.setText("李老师")
        dlg.location.setText("教三-101")
        dlg._save()
        self.assertIsNotNone(dlg.result_course)
        self.assertEqual(dlg.result_course.name, "离散数学")
        self.assertEqual(dlg.result_course.day, 2)
        self.assertEqual(dlg.result_course.start, 3)
        self.assertEqual(dlg.result_course.teacher, "李老师")

    def test_course_dialog_requires_name(self):
        dlg = dialogs.CourseDialog(self.win, self.win.data, None, 1, 1)
        before = dlg.result_course
        dlg._save()
        self.assertIsNone(before)
        self.assertIsNone(dlg.result_course)

    def test_exam_dialog_save(self):
        dlg = dialogs.ExamDialog(self.win, self.win.data, None)
        dlg.name.setText("大学物理（二）")
        dlg._save()
        self.assertIsNotNone(dlg.result_exam)
        self.assertEqual(dlg.result_exam.name, "大学物理（二）")
        self.assertEqual(dlg.result_exam.start_time, "09:00")

    def test_settings_edits_do_not_rebuild_self(self):
        self.win.go(7)
        st = self.win.settings_page
        first_row = st._period_rows[0]
        st.total_weeks.setText("16")
        st._on_total_weeks()
        self.assertEqual(self.win.data.settings.total_weeks, 16)
        st._set_period(0, "start", QTime(9, 5))
        self.assertEqual(self.win.data.periods[0].start, "09:05")
        # 编辑节次时不应重建行、抢走焦点
        self.assertIs(st._period_rows[0], first_row)

    def test_glass_slider_updates_setting(self):
        self.win.go(7)
        self.win.settings_page._on_glass(88)
        self.assertEqual(self.win.data.settings.glass, 88)

    def test_glass_backdrop_rebuilds_quickly(self):
        self.win.go(7)
        before = self.win._backdrop.cacheKey()
        self.win.settings_page._on_glass(92)
        # 背景是 16ms 合并重绘；进程繁忙时固定 qWait 时长可能收不到该定时器，
        # 因此轮询到落地（最多 1s）再断言。
        deadline = 1000
        while self.win._glass_ver != 92 and deadline > 0:
            QTest.qWait(20)
            deadline -= 20
        self.assertEqual(self.win._glass_ver, 92)
        self.assertNotEqual(self.win._backdrop.cacheKey(), before)

    def test_empty_state_pages(self):
        self.win.data.courses.clear()
        self.win.data.exams.clear()
        self.win.data.sample = False
        self.win._refresh_pages()
        for index in (1, 2, 3):
            self.win.go(index)
            self.app.processEvents()
            self.assertFalse(self.win.grab().isNull())

    def test_hide_weekend(self):
        self.win.go(1)
        self.win.data.settings.show_weekend = False
        self.win.schedule_page.set_data(self.win.data, self.win.week)
        self.assertEqual(len(self.win.schedule_page.timetable.days), 5)
        self.assertEqual(len(self.win.schedule_page.header_row.days), 5)

    def test_sticky_header_syncs_horizontal_scroll(self):
        self.win.go(1)
        self.win.resize(1040, 760)
        QApplication.processEvents()
        sp = self.win.schedule_page
        self.assertFalse(sp.timetable.show_head)
        self.assertEqual(sp.header_row.height(), 46)
        hbar = sp.scroll.horizontalScrollBar()
        self.assertGreater(hbar.maximum(), 0)
        hbar.setValue(hbar.maximum())
        QApplication.processEvents()
        self.assertEqual(sp.header_row.offset, hbar.maximum())

    def test_duplicate_and_delete_exam(self):
        self.win.go(3)
        exam = self.win.data.exams[0]
        before = len(self.win.data.exams)
        self.win.duplicate_exam(exam)
        self.assertEqual(len(self.win.data.exams), before + 1)
        self.assertTrue(self.win.data.exams[-1].name.endswith("（副本）"))
        target = self.win.data.exams[-1]
        from campus_planner import widgets
        original = widgets.ask_confirm
        widgets.ask_confirm = lambda *a, **k: True
        try:
            self.win.delete_exam(target)
        finally:
            widgets.ask_confirm = original
        self.assertEqual(len(self.win.data.exams), before)
        self.assertNotIn(target, self.win.data.exams)

    def test_save_and_reload(self):
        self.win.data.courses[0].name = "测试课程 X"
        self.win._save_now()
        reloaded = core.load_data()
        self.assertEqual(reloaded.courses[0].name, "测试课程 X")

    def test_total_weeks_keeps_course_periods(self):
        self.win.go(7)
        st = self.win.settings_page
        course = next(c for c in self.win.data.courses if c.start >= 3)
        before = (course.start, course.end)
        st.total_weeks.setText("4")
        st._on_total_weeks()
        self.assertEqual((course.start, course.end), before)

    def test_period_duration_feedback(self):
        self.win.go(7)
        st = self.win.settings_page
        row = st._period_rows[0]
        dur = row.findChildren(QLabel)[-1]
        st._set_period(0, "end", QTime(7, 30))
        self.assertEqual(dur.text(), "时间有误")
        st._set_period(0, "start", QTime(8, 0))
        st._set_period(0, "end", QTime(8, 45))
        self.assertEqual(dur.text(), "45 分钟")
        self.assertEqual(self.win.data.periods[0].end, "08:45")



    def test_todo_add_toggle_delete(self):
        self.win.go(2)
        page = self.win.todo_page
        before = len(self.win.data.tasks)
        page.input.setText("写一段测试待办")
        page._add_task()
        self.assertEqual(len(self.win.data.tasks), before + 1)
        task = self.win.data.tasks[-1]
        self.assertEqual(task.text, "写一段测试待办")
        page._toggle(task)
        self.assertTrue(task.done)
        self.assertIn(core.date.today().isoformat(), task.history)
        from campus_planner import widgets
        original = widgets.ask_confirm
        widgets.ask_confirm = lambda *a, **k: True
        try:
            page._delete(task)
        finally:
            widgets.ask_confirm = original
        self.assertNotIn(task, self.win.data.tasks)

    def test_about_and_changelog_dialogs(self):
        from campus_planner.about_dialogs import AboutDialog, ChangelogDialog
        about = AboutDialog(self.win)
        self.assertGreater(about.width(), 480)
        texts = [lab.text() for lab in about.findChildren(QLabel)]
        self.assertTrue(any("TonyDash学习终端" in t for t in texts))
        log = ChangelogDialog(self.win)
        browser = log.findChild(QTextBrowser)
        self.assertIsNotNone(browser)
        plain = browser.toPlainText()
        self.assertIn("Beta 1.0", plain)
        self.assertIn("Beta 1.1", plain)
        self.assertIn("Beta 1.2", plain)
        self.assertIn("Beta 1.3", plain)
        about.close()
        log.close()

    def test_home_clock_and_greeting(self):
        self.win.go(0)
        hp = self.win.home_page
        self.assertRegex(hp.clock.text(), r"^\d{2}:\d{2}$")
        self.assertGreaterEqual(hp.seconds.font().pixelSize(), 20)
        self.assertTrue(hp.greeting.text())
        self.assertEqual(hp.week_chip.text(), f"第 {self.win.week} 周")
        clock_base = hp.clock.geometry().top() + hp.clock.fontMetrics().ascent()
        sec_base = hp.seconds.mapTo(hp, QPoint(0, 0)).y() + hp.seconds.fontMetrics().ascent()
        self.assertEqual(clock_base, sec_base)

    def test_split_progress_bar_ratio(self):
        from campus_planner import widgets
        bar = widgets.SplitProgressBar()
        bar.set_ratio(3, 4, animate=False)
        self.assertAlmostEqual(bar.ratio(), 0.75, places=3)
        bar.set_ratio(0, 0, animate=False)
        self.assertEqual(bar.ratio(), 0.0)

    def test_date_field_opens_light_calendar(self):
        from campus_planner import widgets
        field = widgets.DateField()
        field.setDate(QDate.currentDate())
        field.show()
        self.app.processEvents()
        field._open_calendar()
        self.app.processEvents()
        self.assertIsNotNone(field._popup)
        self.assertTrue(field._popup.isVisible())
        self.assertEqual(field._popup.cal.palette().window().color().name(), "#ffffff")
        field._popup.close()
        field.close()

    def test_calendar_popup_background_is_opaque(self):
        """QCalendarWidget 吃带 alpha 的 rgba 背景会被合成到纯黑上（整块日历变黑），
        所以日历自身的样式与调色板必须用不透明颜色。"""
        from campus_planner import theme, widgets
        for mode in ("light", "dark"):
            theme.set_theme(mode)
            pop = widgets.CalendarPopup()
            qss = pop.cal.styleSheet()
            self.assertNotIn("background: rgba(", qss)
            self.assertIn(theme.popup_solid(), qss)
            self.assertEqual(pop.cal.palette().base().color().name(),
                             theme.popup_solid().lower())
            pop.close()
        theme.set_theme("light")
        theme.apply_global_qss(force=True)

    def test_term_start_updates_rail_week(self):
        """改了「开学第一周周一」之后，左栏的当前周次与进度条要立刻跟着变。"""
        self.win.go(7)
        page = self.win.settings_page
        before = self.win.week_bar.value()
        self.win.week = 9
        self.win._sync_chrome()
        self.assertEqual(self.win.week_bar.value(), 50)
        page.term_start.setDate(QDate.currentDate())
        self.app.processEvents()
        self.assertEqual(self.win.week, 1)
        self.assertEqual(self.win.week_bar.value(),
                         int(1 / self.win.data.settings.total_weeks * 100))
        self.assertNotEqual(self.win.week_bar.value(), before)
        self.assertEqual(page.term_start.date().dayOfWeek(), 1)

    def test_blank_window_starts_empty(self):
        from campus_planner.main import MainWindow
        core.data_path().unlink(missing_ok=True)
        win = MainWindow()
        win.show()
        self.app.processEvents()
        self.assertFalse(win.data.courses)
        self.assertFalse(win.data.exams)
        self.assertFalse(win.data.tasks)
        self.assertEqual(len(win.data.periods), 12)
        win.close()

    def test_long_task_title_elides(self):
        from campus_planner import widgets
        from campus_planner.pages.todo import TaskCard
        long_text = "这是一条非常非常长的待办事项标题用来测试它会不会把右侧的勾选框挤出卡片之外" * 2
        card = TaskCard(core.Task("t-long", long_text, "once", deadline="2026-11-05"))
        card.resize(420, 64)
        card.show()
        self.app.processEvents()
        label = card.findChild(widgets.ElidedLabel)
        self.assertIsNotNone(label)
        self.assertTrue(label.text().endswith("…"))
        self.assertLess(card.sizeHint().width(), 600)
        card.close()

    def test_todo_nav_mapping(self):
        self.win.go(2)
        self.assertTrue(self.win.nav_buttons[2].isChecked())
        self.win.go(3)
        self.assertTrue(self.win.nav_buttons[3].isChecked())
        self.win.go(0)
        self.assertTrue(self.win.nav_buttons[0].isChecked())


    def test_empty_schedule_uses_central_panel(self):
        self.win.go(1)
        sp = self.win.schedule_page
        self.win.data.courses.clear()
        sp.set_data(self.win.data, self.win.week)
        self.app.processEvents()
        self.assertTrue(sp.empty_panel.isVisible())
        self.assertFalse(sp.scroll.isVisible())
        self.win.data.courses = core.sample_data().courses
        sp.set_data(self.win.data, self.win.week)
        self.app.processEvents()
        self.assertFalse(sp.empty_panel.isVisible())
        self.assertTrue(sp.scroll.isVisible())

    def test_exam_empty_hero_is_compact(self):
        self.win.go(3)
        self.win.data.exams.clear()
        self.win._refresh_pages()
        self.app.processEvents()
        ep = self.win.exams_page
        self.assertEqual(ep.hero.height(), 104)
        self.assertEqual(ep.hero_chips.count(), 0)
        self.assertTrue(ep.hero_add.isVisible())
        self.assertFalse(ep.hero_bar.isVisible())

    def test_home_compact_hides_week_card(self):
        self.win.go(0)
        hp = self.win.home_page
        self.win.resize(1080, 680)
        self.app.processEvents()
        # 680 高：放不下摘要卡 + 周概览，只保留摘要卡
        self.assertFalse(hp.week_card.isVisible())
        heights = [card.height() for card in hp._cards]
        self.assertTrue(all(150 <= h <= 240 for h in heights), heights)
        self.win.resize(1280, 980)
        self.app.processEvents()
        self.assertTrue(hp.week_card.isVisible())


    def test_first_run_shows_coach_then_marks_onboarded(self):
        core.data_path().unlink(missing_ok=True)
        from campus_planner.main import MainWindow
        win = MainWindow()
        win.show()
        self.app.processEvents()
        self.assertFalse(win.data.settings.onboarded)
        win.start_onboarding()
        self.app.processEvents()
        self.assertIsNotNone(win._coach)
        self.assertTrue(win._coach.isVisible())
        self.assertEqual(win._coach.step_label.text().count("/"), 1)
        win._coach._next(); self.app.processEvents()
        self.assertEqual(win.stack.currentIndex(), 2)
        win._coach._next(); self.app.processEvents()
        self.assertEqual(win.stack.currentIndex(), 3)
        win._coach._next(); self.app.processEvents()
        self.assertTrue(win.data.settings.onboarded)
        self.assertIsNone(win._coach)
        win.close()

    def test_home_checklist_tracks_progress(self):
        self.win.go(0)
        hp = self.win.home_page
        empty = core.blank_data()
        empty.settings.checklist_dismissed = False
        hp.set_data(empty)
        self.app.processEvents()
        self.assertTrue(hp.checklist_card.isVisible())
        self.assertEqual(hp.checklist_progress.text(), "0 / 3 已完成")
        self.assertEqual(hp.start_button.label, "添加第一门课程")
        filled = core.sample_data()
        filled.settings.checklist_dismissed = False
        hp.set_data(filled)
        self.app.processEvents()
        self.assertEqual(hp.checklist_progress.text(), "3 / 3 已完成")
        self.assertEqual(hp.start_button.label, "打开课程表")
        hp._dismiss_checklist()
        self.app.processEvents()
        self.assertFalse(hp.checklist_card.isVisible())


if __name__ == "__main__":
    unittest.main()
