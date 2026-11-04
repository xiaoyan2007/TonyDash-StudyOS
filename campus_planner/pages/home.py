"""主页：时间屏幕、问候语与今日概览。"""
from __future__ import annotations

from datetime import date as Date, datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)

from .. import core, theme, widgets
from . import common


def _greeting(hour: int) -> str:
    if 5 <= hour < 11:
        return "早上好"
    if 11 <= hour < 13:
        return "中午好"
    if 13 <= hour < 18:
        return "下午好"
    if 18 <= hour < 23:
        return "晚上好"
    return "夜深了"


def _clear(layout):
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.hide()
            w.setParent(None)
            w.deleteLater()
        elif item.layout() is not None:
            _clear(item.layout())


class HomePage(QWidget):
    navigate = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data: core.AppData | None = None
        self.setStyleSheet("background: transparent;")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        self.hero = widgets.GlassCard(radius=22, alpha=172)
        hero = QVBoxLayout(self.hero)
        hero.setContentsMargins(30, 18, 30, 18)
        hero.setSpacing(3)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        self.eyebrow = QLabel()
        self.eyebrow.setFont(theme.font(12, theme.QFont.Weight.DemiBold))
        self.eyebrow.setStyleSheet(f"color: {theme.C_BLUE}; background: transparent;")
        top.addWidget(self.eyebrow)
        top.addStretch(1)
        self.week_chip = widgets.Chip("第 1 周", "accent")
        top.addWidget(self.week_chip)
        hero.addLayout(top)
        hero.addSpacing(8)

        clock_row = QHBoxLayout()
        clock_row.setContentsMargins(0, 0, 0, 0)
        clock_row.setSpacing(6)
        # 时:分:秒 统一字号，秒用同一基线与冒号连起来
        self.clock = QLabel("--:--")
        self.clock.setFont(theme.font(58, theme.QFont.Weight.Bold))
        self.clock.setStyleSheet(f"color: {theme.C_TEXT}; background: transparent;")
        clock_row.addWidget(self.clock, 0, Qt.AlignmentFlag.AlignBottom)

        self.seconds = self.clock_text = QLabel("00")
        self.seconds.setFont(theme.font(58, theme.QFont.Weight.Bold))
        self.seconds.setStyleSheet(f"color: {theme.C_TEXT}; background: transparent;")
        self.seconds_wrap = self.seconds
        clock_row.addWidget(self.seconds, 0, Qt.AlignmentFlag.AlignBottom)
        clock_row.addSpacing(18)
        self.greeting = QLabel("你好")
        self.greeting.setFont(theme.font(26, theme.QFont.Weight.DemiBold))
        self.greeting.setStyleSheet(f"color: {theme.C_TEXT}; background: transparent;")
        clock_row.addWidget(self.greeting, 0, Qt.AlignmentFlag.AlignBottom)
        clock_row.addStretch(1)

        self._hero_stats = []
        for caption in ("今日课程", "待办未完成", "最近考试"):
            box = QVBoxLayout()
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(0)
            value = QLabel("0")
            value.setFont(theme.font(24, theme.QFont.Weight.DemiBold))
            value.setStyleSheet(f"color: {theme.C_TEXT}; background: transparent;")
            value.setAlignment(Qt.AlignmentFlag.AlignRight)
            cap = QLabel(caption)
            cap.setFont(theme.font(12))
            cap.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
            cap.setAlignment(Qt.AlignmentFlag.AlignRight)
            box.addWidget(value)
            box.addWidget(cap)
            holder = QWidget()
            holder.setStyleSheet("background: transparent;")
            holder.setLayout(box)
            holder.setMinimumWidth(76)
            clock_row.addWidget(holder, 0, Qt.AlignmentFlag.AlignBottom)
            self._hero_stats.append(value)
        hero.addLayout(clock_row)
        hero.addSpacing(7)

        self.sub = QLabel("")
        self.sub.setFont(theme.font(12.5))
        self.sub.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        self.sub.setWordWrap(True)
        hero.addWidget(self.sub)
        hero.addSpacing(12)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        self.start_button = widgets.AppButton("添加第一门课程", "plus", "primary", "md")
        self.start_button.clicked.connect(lambda: self.navigate.emit(1))
        b2 = widgets.AppButton("查看今日待办", "check", "white", "md")
        b2.clicked.connect(lambda: self.navigate.emit(2))
        b3 = widgets.AppButton("查看考试安排", "report", "white", "md")
        b3.clicked.connect(lambda: self.navigate.emit(3))
        actions.addWidget(self.start_button)
        actions.addWidget(b2)
        actions.addWidget(b3)
        actions.addStretch(1)
        self.today_hint = QLabel("")
        self.today_hint.setFont(theme.font(12))
        self.today_hint.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        actions.addWidget(self.today_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        hero.addLayout(actions)
        root.addWidget(self.hero)

        cards = QHBoxLayout()
        cards.setContentsMargins(0, 0, 0, 0)
        cards.setSpacing(14)
        root.addLayout(cards, 1)

        # 今日课程
        self.course_card = widgets.GlassCard(radius=18, alpha=166)
        cc = QVBoxLayout(self.course_card)
        cc.setContentsMargins(20, 17, 20, 17)
        cc.setSpacing(10)
        cc.addLayout(self._card_head("calendar", "今日课程", "course_count"))
        self.course_body = QVBoxLayout()
        self.course_body.setContentsMargins(0, 0, 0, 0)
        self.course_body.setSpacing(8)
        cc.addLayout(self.course_body)
        cc.addStretch(1)
        cfoot = QHBoxLayout()
        cfoot.setSpacing(8)
        self.course_foot = QLabel("")
        self.course_foot.setFont(theme.font(12))
        self.course_foot.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        cfoot.addWidget(self.course_foot, 1)
        cbtn = widgets.AppButton("打开课程表", "right", "soft", "sm")
        cbtn.clicked.connect(lambda: self.navigate.emit(1))
        cfoot.addWidget(cbtn)
        cc.addLayout(cfoot)
        cards.addWidget(self.course_card, 1)

        # 待办进度
        self.todo_card = widgets.GlassCard(radius=18, alpha=166)
        tc = QVBoxLayout(self.todo_card)
        tc.setContentsMargins(20, 17, 20, 17)
        tc.setSpacing(10)
        tc.addLayout(self._card_head("list", "待办进度", "todo_count"))
        num_row = QHBoxLayout()
        num_row.setContentsMargins(0, 0, 0, 0)
        num_row.setSpacing(6)
        self.todo_big = QLabel("0")
        self.todo_big.setFont(theme.font(30, theme.QFont.Weight.Bold))
        self.todo_big.setStyleSheet(f"color: {theme.C_TEXT}; background: transparent;")
        num_row.addWidget(self.todo_big)
        self.todo_total = QLabel("/ 0 已完成")
        self.todo_total.setFont(theme.font(12))
        self.todo_total.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        num_row.addWidget(self.todo_total, 0, Qt.AlignmentFlag.AlignBottom)
        num_row.addStretch(1)
        tc.addLayout(num_row)
        self.todo_bar = widgets.SplitProgressBar(height=7)
        tc.addWidget(self.todo_bar)
        self.todo_body = QVBoxLayout()
        self.todo_body.setContentsMargins(0, 0, 0, 0)
        self.todo_body.setSpacing(6)
        tc.addLayout(self.todo_body)
        tc.addStretch(1)
        tfoot = QHBoxLayout()
        tfoot.setSpacing(8)
        self.todo_foot = QLabel("")
        self.todo_foot.setFont(theme.font(12))
        self.todo_foot.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        tfoot.addWidget(self.todo_foot, 1)
        tbtn = widgets.AppButton("打开待办", "right", "soft", "sm")
        tbtn.clicked.connect(lambda: self.navigate.emit(2))
        tfoot.addWidget(tbtn)
        tc.addLayout(tfoot)
        cards.addWidget(self.todo_card, 1)

        # 最近考试
        self.exam_card = widgets.GlassCard(radius=18, alpha=166)
        ec = QVBoxLayout(self.exam_card)
        ec.setContentsMargins(20, 17, 20, 17)
        ec.setSpacing(8)
        ec.addLayout(self._card_head("report", "最近考试", "exam_count"))
        self.exam_name = QLabel("暂无考试")
        self.exam_name.setFont(theme.font(14, theme.QFont.Weight.DemiBold))
        self.exam_name.setStyleSheet(f"color: {theme.C_TEXT}; background: transparent;")
        self.exam_name.setWordWrap(True)
        ec.addWidget(self.exam_name)
        self.exam_days = QLabel("")
        self.exam_days.setFont(theme.font(12))
        self.exam_days.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        self.exam_days.setWordWrap(True)
        ec.addWidget(self.exam_days)
        self.exam_meta = QLabel("")
        self.exam_meta.setFont(theme.font(12))
        self.exam_meta.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        self.exam_meta.setWordWrap(True)
        ec.addWidget(self.exam_meta)
        self.exam_prog_label = QLabel("复习进度 0%")
        self.exam_prog_label.setFont(theme.font(11.5))
        self.exam_prog_label.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        ec.addWidget(self.exam_prog_label)
        self.exam_prog = widgets.ProgressBar(value=0, color=theme.C_BLUE, height=6)
        ec.addWidget(self.exam_prog)
        ec.addStretch(1)
        self.exam_btn = widgets.AppButton("考试安排", "right", "soft", "sm")
        self.exam_btn.clicked.connect(lambda: self.navigate.emit(3))
        ec.addWidget(self.exam_btn, 0, Qt.AlignmentFlag.AlignLeft)
        cards.addWidget(self.exam_card, 1)
        self._cards = [self.course_card, self.todo_card, self.exam_card]

        self.checklist_card = widgets.GlassCard(radius=16, alpha=170)
        cl = QVBoxLayout(self.checklist_card)
        cl.setContentsMargins(20, 12, 20, 12)
        cl.setSpacing(7)
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(widgets.IconLabel("spark", 15, theme.C_BLUE))
        t = QLabel("上手清单")
        t.setFont(theme.font(12, theme.QFont.Weight.DemiBold))
        t.setStyleSheet(f"color: {theme.C_TEXT}; background: transparent;")
        head.addWidget(t)
        head.addStretch(1)
        self.checklist_progress = QLabel("")
        self.checklist_progress.setFont(theme.font(12))
        self.checklist_progress.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        head.addWidget(self.checklist_progress)
        close = widgets.AppButton("", "close", "ghost", "icon")
        close.setFixedSize(28, 28)
        close.setToolTip("不再显示上手清单")
        close.clicked.connect(self._dismiss_checklist)
        head.addWidget(close)
        cl.addLayout(head)
        self.checklist_rows = QHBoxLayout()
        self.checklist_rows.setContentsMargins(0, 0, 0, 0)
        self.checklist_rows.setSpacing(10)
        cl.addLayout(self.checklist_rows)
        self._checklist_items = [
            ("course", "建第一门课", "课程表 → 点空白格子或「新增课程」", 1),
            ("task", "加第一条待办", "待办 → 输入一行按回车", 2),
            ("exam", "记第一场考试", "期末考试 → 新增考试", 3),
        ]
        root.addWidget(self.checklist_card)

        self.week_card = widgets.GlassCard(radius=16, alpha=150)
        self.week_card.setFixedHeight(112)
        wc = QVBoxLayout(self.week_card)
        wc.setContentsMargins(20, 10, 20, 9)
        wc.setSpacing(5)
        wh = QHBoxLayout()
        wh.setSpacing(8)
        wh.addWidget(widgets.IconLabel("calendar", 14, theme.C_BLUE))
        wtitle = QLabel("本周概览")
        wtitle.setFont(theme.font(13, theme.QFont.Weight.DemiBold))
        wtitle.setStyleSheet(f"color: {theme.C_TEXT}; background: transparent;")
        wh.addWidget(wtitle)
        wh.addStretch(1)
        self.week_sum = QLabel("")
        self.week_sum.setFont(theme.font(11.5))
        self.week_sum.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        wh.addWidget(self.week_sum)
        wc.addLayout(wh)
        self.week_body = QHBoxLayout()
        self.week_body.setContentsMargins(0, 0, 0, 0)
        self.week_body.setSpacing(8)
        wc.addLayout(self.week_body)
        root.addWidget(self.week_card)
        root.addStretch(1)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._tick()

    # -- 布局
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "_cards"):
            return
        self._fit_layout()

    def _fit_layout(self):
        """卡片高度保持稳定；空间不足时先收起周概览。"""
        if not hasattr(self, "_cards"):
            return
        hero_h = self.hero.sizeHint().height()
        checklist = self.checklist_card.isVisible()
        checklist_h = (self.checklist_card.sizeHint().height() + 14) if checklist else 0
        room = self.height() - hero_h - checklist_h - 14 * 3
        week_h = 112 + 14
        if room < 200:
            # 极端高度下先收起清单，保证摘要卡可见
            self.checklist_card.setVisible(False)
            checklist_h = 0
            room = self.height() - hero_h - 14 * 3
        card_h = 240 if room >= 240 else max(150, min(240, room))
        show_week = room >= card_h + week_h
        for card in self._cards:
            if card.height() != card_h:
                card.setFixedHeight(card_h)
        self.week_card.setVisible(show_week)

    # -- 小工具
    def _card_head(self, icon: str, title: str, count_attr: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(widgets.IconLabel(icon, 14, theme.C_BLUE))
        lab = QLabel(title)
        lab.setFont(theme.font(13, theme.QFont.Weight.DemiBold))
        lab.setStyleSheet(f"color: {theme.C_TEXT}; background: transparent;")
        row.addWidget(lab)
        row.addStretch(1)
        chip = widgets.Chip("", "neutral")
        row.addWidget(chip)
        setattr(self, count_attr, chip)
        return row

    def _tick(self):
        now = datetime.now()
        self.clock.setText(now.strftime("%H:%M"))
        self.seconds.setText(f":{now.second:02d}")
        self.greeting.setText(_greeting(now.hour))
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        self.eyebrow.setText(f"{now.year} 年 {now.month} 月 {now.day} 日 · {weekdays[now.weekday()]}")

    # -- 数据
    def set_data(self, data: core.AppData):
        self.data = data
        self._tick()
        self._sync_step_button()
        self._render_checklist()
        today = Date.today()
        week = core.current_week(data.settings.term_start, data.settings.total_weeks, today)
        self.week_chip.setText(f"第 {week} 周")

        todays: list[core.Course] = []
        for c in data.courses:
            if c.day == today.isoweekday() and core.course_in_week(c, week, data.settings.total_weeks):
                todays.append(c)
        todays.sort(key=lambda c: c.start)
        self._render_courses(todays)
        self._render_todos()
        self._render_exam()
        self._render_week(week, todays)
        total, done, _pending = core.task_stats(data.tasks)
        parts = []
        if todays:
            parts.append(f"今天有 {len(todays)} 门课")
        else:
            parts.append("今天没有课")
        if total:
            parts.append(f"{done} / {total} 条待办已完成")
        upcoming = core.upcoming_exams(data.exams)
        if upcoming:
            parts.append(f"下一场考试还有 {core.days_until(upcoming[0].date_obj(), today)} 天")
        self.sub.setText("　·　".join(parts))
        self.today_hint.setText("慢慢来，比较快" if not todays else "按自己的节奏来")

        _total, _done, pending = core.task_stats(data.tasks)
        self._hero_stats[0].setText(str(len(todays)))
        self._hero_stats[1].setText(str(pending))
        gap = core.days_until(upcoming[0].date_obj(), today) if upcoming else None
        self._hero_stats[2].setText(f"{gap} 天" if gap is not None else "—")

    def _sync_step_button(self):
        """方案四：空数据时主按钮是「添加第一门课程」，有课后变成「打开课程表」。"""
        has_courses = bool(self.data and self.data.courses)
        self.start_button.label = "打开课程表" if has_courses else "添加第一门课程"
        self.start_button.icon_name = "calendar" if has_courses else "plus"
        self.start_button.update()

    def _documented(self) -> bool:
        s = getattr(self, "data", None)
        return bool(s and s.settings.checklist_dismissed)

    def _dismiss_checklist(self):
        if self.data:
            self.data.settings.checklist_dismissed = True
            self.checklist_card.hide()
            self._fit_layout()

    def _render_checklist(self):
        _clear(self.checklist_rows)
        if not self.data or self._documented():
            self.checklist_card.hide()
            return
        done = {
            "course": bool(self.data.courses),
            "task": bool(self.data.tasks),
            "exam": bool(self.data.exams),
        }
        finished = sum(1 for v in done.values() if v)
        self.checklist_progress.setText(f"{finished} / 3 已完成")
        for key, title, hint, page in self._checklist_items:
            row = QWidget()
            row.setStyleSheet("background: transparent;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(7)
            is_done = done[key]
            icon = widgets.IconLabel("check" if is_done else "right", 13,
                                     theme.C_GREEN if is_done else theme.C_BLUE)
            rl.addWidget(icon)
            col = QVBoxLayout()
            col.setSpacing(0)
            name = QLabel(title)
            name.setFont(theme.font(13, theme.QFont.Weight.DemiBold))
            name.setStyleSheet(
                f"color: {theme.C_SUB if is_done else theme.C_TEXT}; background: transparent;")
            if is_done:
                f = name.font()
                f.setStrikeOut(True)
                name.setFont(f)
            col.addWidget(name)
            desc = QLabel(hint)
            desc.setFont(theme.font(12))
            desc.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
            col.addWidget(desc)
            rl.addLayout(col, 1)
            if not is_done:
                go = widgets.AppButton("去完成", None, "white", "sm")
                go.clicked.connect(lambda _=False, p=page: self.navigate.emit(p))
                rl.addWidget(go)
            self.checklist_rows.addWidget(row, 1)
        self.checklist_card.show()
        self._fit_layout()

    def _render_courses(self, todays: list[core.Course]):
        _clear(self.course_body)
        self.course_count.setText(f"{len(todays)} 门")
        if not todays:
            hint = QLabel("今天没有课，享受空白的一天。")
            hint.setFont(theme.font(12))
            hint.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
            hint.setWordWrap(True)
            self.course_body.addWidget(hint)
            return
        for c in todays[:4]:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            dot = QLabel("")
            dot.setFixedSize(6, 6)
            dot.setStyleSheet(f"background: {theme.course_color(c.color).name()}; border-radius: 3px;")
            row.addWidget(dot)
            t = QLabel(c.time_text(self.data.periods).replace("–", " - "))
            t.setFont(theme.font(12, theme.QFont.Weight.DemiBold))
            t.setStyleSheet(f"color: {theme.C_TEXT}; background: transparent;")
            row.addWidget(t)
            name = QLabel(c.name)
            name.setFont(theme.font(12))
            name.setStyleSheet(f"color: {theme.C_TEXT}; background: transparent;")
            name.setWordWrap(True)
            row.addWidget(name, 1)
            loc = QLabel(c.location)
            loc.setFont(theme.font(11))
            loc.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
            row.addWidget(loc)
            box = QWidget()
            box.setStyleSheet("background: transparent;")
            box.setLayout(row)
            self.course_body.addWidget(box)

    def _render_week(self, week: int, todays: list[core.Course]):
        _clear(self.week_body)
        names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        today = Date.today()
        total_courses = 0
        total_periods = 0
        counts = []
        for day in range(1, 8):
            day_courses = [c for c in self.data.courses
                           if c.day == day and core.course_in_week(c, week, self.data.settings.total_weeks)]
            counts.append(day_courses)
            total_courses += len(day_courses)
            total_periods += sum(c.end - c.start + 1 for c in day_courses)
        self.week_sum.setText(f"本周 {total_courses} 门课 · {total_periods} 节课")
        for idx, courses in enumerate(counts):
            d = core.date_of_week_day(self.data.settings.term_start, week, idx + 1)
            is_today = d == today
            box = QWidget()
            box.setStyleSheet(
                "background: rgba(10,132,255,20); border-radius: 9px;"
                if is_today else "background: transparent; border-radius: 9px;"
            )
            bl = QVBoxLayout(box)
            bl.setContentsMargins(8, 6, 8, 6)
            bl.setSpacing(1)
            day_label = QLabel(names[idx])
            day_label.setFont(theme.font(11.5, theme.QFont.Weight.DemiBold
                                         if is_today else theme.QFont.Weight.Normal))
            day_label.setStyleSheet(
                f"color: {theme.C_BLUE if is_today else theme.C_SUB}; background: transparent;")
            day_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bl.addWidget(day_label)
            num = QLabel(str(d.day))
            num.setFont(theme.font(14.5, theme.QFont.Weight.DemiBold))
            num.setStyleSheet(
                f"color: {theme.C_BLUE if is_today else theme.C_TEXT}; background: transparent;")
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bl.addWidget(num)
            cnt = QLabel(f"{len(courses)} 节" if courses else "—")
            cnt.setFont(theme.font(11.5))
            cnt.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
            cnt.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bl.addWidget(cnt)
            self.week_body.addWidget(box, 1)

    def _render_todos(self):
        _clear(self.todo_body)
        total, done, pending = core.task_stats(self.data.tasks)
        self.todo_count.setText(f"共 {total} 条")
        self.todo_big.setText(str(pending))
        self.todo_total.setText(f"/ {total} 条未完成")
        self.todo_bar.set_ratio(done, total, animate=False)
        pct = round(done * 100 / total) if total else 0
        self.todo_foot.setText(f"已完成 {done} / {total} 条 · {pct}%")
        items = [t for t in core.sorted_tasks(self.data.tasks) if not t.done][:4]
        if not items:
            hint = QLabel("还没有待办，先加一条今天要做的事。"
                          if total == 0 else "待办已经清空，今天可以安心收工。")
            hint.setFont(theme.font(12))
            hint.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
            hint.setWordWrap(True)
            self.todo_body.addWidget(hint)
            return
        for t in items:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(7)
            dot = QLabel("")
            dot.setFixedSize(5, 5)
            dot.setStyleSheet(f"background: {theme.C_BLUE}; border-radius: 2px;")
            row.addWidget(dot)
            text = QLabel(t.text)
            text.setFont(theme.font(12))
            text.setStyleSheet(f"color: {theme.C_TEXT}; background: transparent;")
            text.setWordWrap(True)
            row.addWidget(text, 1)
            kind = QLabel(core.TASK_TYPE_LABELS.get(t.type, ""))
            kind.setFont(theme.font(11.5))
            kind.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
            row.addWidget(kind)
            box = QWidget()
            box.setStyleSheet("background: transparent;")
            box.setLayout(row)
            self.todo_body.addWidget(box)

    def _render_exam(self):
        exams = core.upcoming_exams(self.data.exams)
        self.exam_count.setText(f"{len(exams)} 场待考")
        if not exams:
            self.exam_name.setText("暂无考试安排")
            self.exam_days.setText("期末还很远，先把眼前的日子过好。")
            self.exam_meta.setText("")
            self.exam_prog_label.setText("复习进度 —")
            self.exam_prog.setValue(0)
            self.exam_btn.setVisible(False)
            return
        self.exam_btn.setVisible(True)
        e = exams[0]
        days = core.days_until(e.date_obj())
        self.exam_name.setText(e.name)
        self.exam_days.setText(f"还有 {days} 天　{core.format_cn_date(e.date_obj())} {core.format_weekday(e.date_obj())}")
        self.exam_meta.setText(f"{e.start_time}–{e.end_time()}　{e.location or '地点待定'}")
        self.exam_prog_label.setText(f"复习进度 {e.progress}%")
        self.exam_prog.setValue(e.progress)
