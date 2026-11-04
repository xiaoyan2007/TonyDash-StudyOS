"""期末考试页面：倒计时、统计、筛选与考试卡片。"""
from __future__ import annotations

from datetime import date as Date, datetime

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QLayout,
    QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from .. import core, theme, widgets
from . import common

STATUS_TEXT = {"wait": "待考", "live": "进行中", "done": "已结束"}
SORTS = [("time", "按时间"), ("credits", "按学分"), ("name", "按名称")]


class ExamCard(widgets.GlassCard):
    def __init__(self, exam: core.Exam, status: str, on_edit, on_dup, on_delete,
                 conflicts: list[core.Exam] | None = None, parent=None):
        super().__init__(parent, radius=14, alpha=142)
        self.exam = exam
        self.status = status
        self._on_edit = on_edit
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background: transparent;")
        d = exam.date_obj() or Date.today()
        base = QColor(theme.course_color(exam.color))
        done = status == "done"

        lay = QHBoxLayout(self)
        lay.setContentsMargins(15, 12, 13, 12)
        lay.setSpacing(12)

        date_box = QVBoxLayout()
        date_box.setSpacing(0)
        day = QLabel(str(d.day))
        day.setFont(theme.font(21, theme.QFont.Weight.Bold))
        day.setStyleSheet(f"color: {theme.C_SUB if done else theme.C_TEXT}; background: transparent;")
        day.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        month = QLabel(f"{d.month} 月")
        month.setFont(theme.font(11))
        month.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        month.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        date_box.addWidget(day)
        date_box.addWidget(month)
        date_wrap = QWidget()
        date_wrap.setLayout(date_box)
        date_wrap.setFixedWidth(58)
        date_wrap.setStyleSheet("background: transparent;")
        lay.addWidget(date_wrap)

        divider = QFrame()
        divider.setFixedWidth(1)
        divider.setStyleSheet(theme.divider_style(18))
        lay.addWidget(divider)

        info = QVBoxLayout()
        info.setSpacing(4)
        title_row = QHBoxLayout()
        title_row.setSpacing(7)
        name = QLabel(exam.name)
        name.setFont(theme.font(13.5, theme.QFont.Weight.DemiBold))
        name.setStyleSheet(f"color: {theme.C_SUB if done else theme.C_TEXT}; background: transparent;")
        title_row.addWidget(name)
        type_chip = widgets.Chip(exam.type or "考试", "accent" if not done else "neutral")
        title_row.addWidget(type_chip)
        if conflicts:
            title_row.addWidget(widgets.Chip("时间重叠", "red", "warning"))
        title_row.addStretch(1)
        info.addLayout(title_row)

        meta_text = f"{exam.time_range()} · {exam.duration} 分钟"
        if exam.location:
            meta_text += f" · {exam.location}"
        if exam.seat:
            meta_text += f" · 座位 {exam.seat}"
        if exam.credits:
            meta_text += f" · {exam.credits:g} 学分"
        meta = QLabel(meta_text)
        meta.setFont(theme.font(12))
        meta.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        info.addWidget(meta)

        custom = [f for f in exam.custom if f.label or f.value]
        if custom:
            row = QHBoxLayout()
            row.setSpacing(6)
            for f in custom[:3]:
                text = f"{f.label}：{f.value}" if f.label else f.value
                row.addWidget(widgets.Chip(text, "white"))
            row.addStretch(1)
            info.addLayout(row)
        if exam.note:
            note = QLabel(exam.note)
            note.setFont(theme.font(11.5))
            note.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
            fm = QFontMetrics(note.font())
            note.setText(fm.elidedText(exam.note, Qt.TextElideMode.ElideRight, 520))
            info.addWidget(note)

        prog_row = QHBoxLayout()
        prog_row.setSpacing(8)
        bar = widgets.ProgressBar(exam.progress if not done else 100,
                                  height=4,
                                  color=theme.C_SUB if done else theme.C_BLUE)
        bar.setFixedWidth(110)
        prog_row.addWidget(bar)
        prog = QLabel(f"复习 {exam.progress}%")
        prog.setFont(theme.font(11))
        prog.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        prog_row.addWidget(prog)
        prog_row.addStretch(1)
        info.addLayout(prog_row)
        lay.addLayout(info, 1)

        side = QVBoxLayout()
        side.setSpacing(5)
        side.setAlignment(Qt.AlignmentFlag.AlignRight)
        kind = {"wait": "accent", "live": "green", "done": "neutral"}[status]
        status_chip = widgets.Chip(STATUS_TEXT[status], kind)
        side.addWidget(status_chip, 0, Qt.AlignmentFlag.AlignRight)
        rel = QLabel(core.relative_day_text(d))
        rel.setFont(theme.font(11, theme.QFont.Weight.DemiBold if status == "wait" else theme.QFont.Weight.Normal))
        rel.setStyleSheet(f"color: {theme.C_BLUE if status == 'wait' else theme.C_SUB}; background: transparent;")
        side.addWidget(rel, 0, Qt.AlignmentFlag.AlignRight)
        side.addStretch(1)
        buttons = QHBoxLayout()
        buttons.setSpacing(3)
        edit = widgets.AppButton("", "edit", "ghost", "icon")
        edit.setToolTip("编辑")
        edit.clicked.connect(lambda: on_edit(exam))
        dup = widgets.AppButton("", "copy", "ghost", "icon")
        dup.setToolTip("复制")
        dup.clicked.connect(lambda: on_dup(exam))
        delete = widgets.AppButton("", "trash", "ghost", "icon")
        delete.setToolTip("删除")
        delete.clicked.connect(lambda: on_delete(exam))
        for b in (edit, dup, delete):
            buttons.addWidget(b)
        side.addLayout(buttons)
        lay.addLayout(side)

        extra = (24 if custom else 0) + (18 if exam.note else 0)
        self.setFixedHeight(110 + extra)

        # 左侧色条由 paintEvent 叠加
        self._bar = base

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._bar)
        radius = 14
        p.drawRoundedRect(QRectF(1.6, 12, 3.4, self.height() - 24), 1.7, 1.7)
        p.end()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_edit(self.exam)
        super().mouseReleaseEvent(event)


class ExamPage(QWidget):
    new_exam = Signal()
    edit_exam = Signal(object)
    duplicate_exam = Signal(object)
    delete_exam = Signal(object)
    export_ics = Signal()
    refresh_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self.data: core.AppData | None = None
        self.filter = "all"
        self.query = ""
        self.sort = "time"
        self._next: core.Exam | None = None
        self._last_status = ""
        self._build()
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # -- 构建
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        self.header = common.PageHeader("", "期末考试", hint="点「新增考试」记录时间；点考试卡片可编辑，支持导出 .ics 日历")
        export = widgets.AppButton("导出日历", "download", "ghost", "md")
        export.clicked.connect(self.export_ics)
        add = widgets.AppButton("新增考试", "plus", "primary", "md")
        add.clicked.connect(self.new_exam)
        self.header.add_action(export)
        self.header.add_action(add)
        root.addWidget(self.header)

        self.hero = widgets.GlassCard(radius=18, alpha=180)
        self.hero.setFixedHeight(154)
        hero = QHBoxLayout(self.hero)
        hero.setContentsMargins(24, 16, 22, 16)
        hero.setSpacing(22)
        left = QVBoxLayout()
        left.setSpacing(1)
        self.cd_caption = widgets.label("距离下一场考试", 12, theme.C_SUB)
        left.addWidget(self.cd_caption)
        row = QHBoxLayout()
        row.setSpacing(7)
        self.cd_days = QLabel("—")
        self.cd_days.setFont(theme.font(43, theme.QFont.Weight.Bold))
        self.cd_days.setStyleSheet(f"color: {theme.C_TEXT}; background: transparent;")
        self.cd_unit = widgets.label("天", 14, theme.C_SUB)
        row.addWidget(self.cd_days)
        row.addWidget(self.cd_unit, 0, Qt.AlignmentFlag.AlignBottom)
        self.cd_clock = QLabel("")
        self.cd_clock.setFont(theme.font(13, theme.QFont.Weight.DemiBold))
        self.cd_clock.setStyleSheet(f"color: {theme.C_BLUE}; background: transparent;")
        row.addWidget(self.cd_clock, 0, Qt.AlignmentFlag.AlignBottom)
        row.addStretch(1)
        left.addLayout(row)
        self.cd_date = widgets.label("", 12, theme.C_SUB)
        left.addWidget(self.cd_date)
        left.addStretch(1)
        hero.addLayout(left, 0)

        self.hero_vline = QFrame()
        self.hero_vline.setFixedWidth(1)
        self.hero_vline.setStyleSheet(theme.divider_style(24))
        hero.addWidget(self.hero_vline)

        right = QVBoxLayout()
        right.setSpacing(6)
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self.hero_name = QLabel("暂无待考考试")
        self.hero_name.setFont(theme.font(17, theme.QFont.Weight.DemiBold))
        self.hero_name.setStyleSheet(f"color: {theme.C_TEXT}; background: transparent;")
        title_row.addWidget(self.hero_name)
        self.hero_chips = QHBoxLayout()
        self.hero_chips.setSpacing(6)
        title_row.addLayout(self.hero_chips)
        title_row.addStretch(1)
        self.hero_add = widgets.AppButton("新增考试", "plus", "primary", "sm")
        self.hero_add.clicked.connect(self.new_exam)
        self.hero_add.hide()
        title_row.addWidget(self.hero_add)
        right.addLayout(title_row)
        self.hero_meta1 = widgets.label("", 11, theme.C_SUB)
        self.hero_meta2 = widgets.label("", 11, theme.C_SUB)
        right.addWidget(self.hero_meta1)
        right.addWidget(self.hero_meta2)
        right.addStretch(1)
        bottom = QHBoxLayout()
        bottom.setSpacing(9)
        self.hero_bar = widgets.ProgressBar(0, height=5)
        self.hero_bar.setFixedWidth(210)
        self.hero_prog = widgets.label("复习 0%", 11.5, theme.C_SUB)
        bottom.addWidget(self.hero_bar)
        bottom.addWidget(self.hero_prog)
        bottom.addStretch(1)
        self.hero_edit = widgets.AppButton("查看考试", "right", "soft", "sm")
        self.hero_edit.clicked.connect(self._edit_next)
        bottom.addWidget(self.hero_edit)
        right.addLayout(bottom)
        hero.addLayout(right, 1)
        root.addWidget(self.hero)

        self.stats_row = QHBoxLayout()
        self.stats_row.setSpacing(10)
        self.stat_pending = widgets.StatTile("待考科目", "0", "门")
        self.stat_credits = widgets.StatTile("待考总学分", "0", "学分")
        self.stat_days = widgets.StatTile("最近一场", "—", "天")
        self.stat_progress = widgets.StatTile("平均复习进度", "0", "%")
        for tile in (self.stat_pending, self.stat_credits, self.stat_days, self.stat_progress):
            tile.setMinimumHeight(94)
            self.stats_row.addWidget(tile)
        root.addLayout(self.stats_row)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.seg = widgets.Segmented([("all", "全部"), ("pending", "待考"), ("done", "已结束")], "all")
        self.seg.changed.connect(self._on_filter)
        bar.addWidget(self.seg)
        bar.addStretch(1)
        self.search = widgets.SearchBox("搜索科目、地点、类型")
        self.search.setMinimumWidth(230)
        self.search.setMaximumWidth(290)
        self.search.textChanged.connect(self._on_search)
        bar.addWidget(self.search)
        self.sort_select = widgets.Select()
        for key, text in SORTS:
            self.sort_select.addItem(text, key)
        self.sort_select.setFixedWidth(124)
        self.sort_select.currentIndexChanged.connect(self._on_sort)
        bar.addWidget(self.sort_select)
        root.addLayout(bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.list_host = QWidget()
        self.list_host.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 2, 4, 4)
        self.list_layout.setSpacing(12)
        self.list_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.scroll.setWidget(self.list_host)
        root.addWidget(self.scroll, 1)

    # -- 数据
    def set_data(self, data: core.AppData):
        self.data = data
        self.header.set_eyebrow(f"{data.settings.term_name} · 考试安排")
        pending = [e for e in data.exams if core.exam_status(e) != "done"]
        avg = round(sum(e.progress for e in pending) / len(pending)) if pending else 0
        self.header.set_subtitle(
            f"共 {len(data.exams)} 场考试 · 待考 {len(pending)} 场 · 平均复习进度 {avg}%"
        )
        next_exam = core.upcoming_exams(data.exams)
        self._next = next_exam[0] if next_exam else None
        self._last_status = core.exam_status(self._next) if self._next else ""
        self._update_hero()
        self._update_stats()
        self._render_list()

    def _update_hero(self):
        exam = self._next
        while self.hero_chips.count():
            item = self.hero_chips.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        if not exam:
            self.hero.setFixedHeight(104)
            self.cd_caption.setText("期末考试")
            self.cd_days.hide()
            self.cd_clock.setText("")
            self.cd_unit.hide()
            self.cd_date.hide()
            self.hero_name.setText("还没有安排考试")
            self.hero_meta1.setText("添加第一场考试后，这里会显示倒计时与复习进度。")
            self.hero_meta2.setText("")
            self.hero_meta1.show()
            self.hero_meta2.hide()
            self.hero_bar.hide()
            self.hero_prog.hide()
            self.hero_edit.hide()
            self.hero_vline.hide()
            self.hero_add.show()
            return
        self.hero.setFixedHeight(154)
        self.cd_caption.setText("距离下一场考试")
        self.cd_days.show()
        self.cd_date.show()
        self.hero_meta2.show()
        self.hero_bar.show()
        self.hero_prog.show()
        self.hero_vline.show()
        self.hero_add.hide()
        self.cd_unit.show()
        self.hero_edit.show()
        status = core.exam_status(exam)
        self.hero_name.setText(exam.name)
        self.hero_chips.addWidget(widgets.Chip(exam.type or "考试", "accent"))
        if exam.credits:
            self.hero_chips.addWidget(widgets.Chip(f"{exam.credits:g} 学分", "neutral"))
        if status == "live":
            self.hero_chips.addWidget(widgets.Chip("正在考试", "green"))
        d = exam.date_obj() or Date.today()
        self.cd_date.setText(f"{core.format_cn_date(d)} {core.format_weekday(d)} · {exam.time_range()}")
        meta1 = f"{exam.time_range()} · {exam.duration} 分钟"
        if exam.location:
            meta1 += f" · {exam.location}"
        if exam.seat:
            meta1 += f" · 座位 {exam.seat}"
        self.hero_meta1.setText(meta1)
        extra = [f"{f.label}：{f.value}" if f.label else f.value for f in exam.custom if f.label or f.value]
        self.hero_meta2.setText(" · ".join(extra) if extra else (exam.note or ""))
        self.hero_bar.setValue(exam.progress)
        self.hero_prog.setText(f"复习 {exam.progress}%")
        self._tick()

    def _update_stats(self):
        if not self.data:
            return
        pending = [e for e in self.data.exams if core.exam_status(e) != "done"]
        credits = sum(e.credits for e in pending)
        gaps = [(e.date_obj() - Date.today()).days for e in pending if e.date_obj()]
        gaps = [g for g in gaps if g >= 0]
        avg = round(sum(e.progress for e in pending) / len(pending)) if pending else 0
        self.stat_pending.set_value(str(len(pending)))
        self.stat_credits.set_value(f"{credits:g}")
        self.stat_days.set_value(str(min(gaps)) if gaps else "—")
        self.stat_progress.set_value(str(avg), theme.C_BLUE if avg else theme.C_TEXT)

    def _tick(self):
        exam = self._next
        if not exam:
            return
        now = datetime.now()
        start = exam.start_dt()
        end = exam.end_dt()
        if not start or not end:
            return
        status = core.exam_status(exam, now)
        if status != self._last_status:
            self._last_status = status
            self.refresh_requested.emit()
            return
        if status == "live":
            self.cd_days.setText("0")
            self.cd_caption.setText("考试进行中")
            delta = end - now
            self.cd_clock.setText(f"剩余 {max(0, int(delta.total_seconds()) // 60)} 分钟")
        elif status == "wait":
            delta = start - now
            days = max(0, delta.days)
            if days:
                self.cd_days.setText(str(days))
                self.cd_caption.setText("距离下一场考试")
            else:
                self.cd_days.setText("0")
                self.cd_caption.setText("今天考试")
            secs = max(0, int(delta.total_seconds()) % 86400)
            self.cd_clock.setText(f"{secs // 3600:02d}:{secs % 3600 // 60:02d}:{secs % 60:02d}")
        else:
            self.cd_days.setText("0")
            self.cd_caption.setText("考试已结束")
            self.cd_clock.setText("")

    def _edit_next(self):
        if self._next:
            self.edit_exam.emit(self._next)

    # -- 交互
    def _on_filter(self, key: str):
        self.filter = key
        self._render_list()

    def _on_search(self, text: str):
        self.query = text.strip()
        self._render_list()

    def _on_sort(self, index: int):
        self.sort = self.sort_select.itemData(index) or "time"
        self._render_list()

    def _visible(self) -> list[core.Exam]:
        if not self.data:
            return []
        exams = list(self.data.exams)
        if self.filter == "pending":
            exams = [e for e in exams if core.exam_status(e) != "done"]
        elif self.filter == "done":
            exams = [e for e in exams if core.exam_status(e) == "done"]
        if self.query:
            q = self.query.lower()
            def hit(e: core.Exam) -> bool:
                parts = [e.name, e.type, e.location, e.note]
                parts += [f"{f.label} {f.value}" for f in e.custom]
                return any(q in (p or "").lower() for p in parts)
            exams = [e for e in exams if hit(e)]
        if self.sort == "credits":
            exams.sort(key=lambda e: (-e.credits, e.start_dt() or datetime.max))
        elif self.sort == "name":
            exams.sort(key=lambda e: e.name)
        else:
            exams.sort(key=lambda e: e.start_dt() or datetime.max)
        return exams

    def _clear_list(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
            else:
                sub = item.layout()
                if sub is not None:
                    while sub.count():
                        child = sub.takeAt(0)
                        w = child.widget()
                        if w is not None:
                            w.hide()
                            w.deleteLater()

    def _render_list(self):
        self._clear_list()
        exams = self._visible()
        if not exams:
            if self.data and not self.data.exams:
                btn = widgets.AppButton("新增第一场考试", "plus", "primary", "md")
                btn.clicked.connect(self.new_exam)
                empty = widgets.EmptyState("report", "还没有考试安排",
                                           "记录考试科目、时间、地点和复习进度，系统会自动生成倒计时。",
                                           action=btn)
                self.list_layout.addWidget(empty)
            else:
                hint = widgets.label("没有符合筛选条件的考试，换个关键词或切回「全部」。",
                                     11, theme.C_SUB)
                hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.list_layout.addWidget(hint)
            self.list_layout.addStretch(1)
            return
        conflicts = {}
        for e in self.data.exams if self.data else []:
            others = core.exam_conflicts(self.data.exams, e)
            if others:
                conflicts[e.id] = others
        groups: dict[str, list[core.Exam]] = {}
        for e in exams:
            groups.setdefault(e.date, []).append(e)
        for date_key, group in groups.items():
            d = group[0].date_obj() or Date.today()
            head = QHBoxLayout()
            head.setContentsMargins(4, 4, 6, 0)
            head.setSpacing(8)
            title = widgets.label(f"{core.format_cn_date(d)} · {core.format_weekday(d)}",
                                  11.5, theme.C_TEXT, theme.QFont.Weight.DemiBold)
            head.addWidget(title)
            head.addWidget(widgets.Chip(core.relative_day_text(d), "white"))
            if len(group) > 1:
                head.addWidget(widgets.Chip(f"{len(group)} 场", "amber"))
            head.addStretch(1)
            self.list_layout.addLayout(head)
            for e in group:
                status = core.exam_status(e)
                card = ExamCard(e, status, self.edit_exam.emit,
                                self.duplicate_exam.emit, self.delete_exam.emit,
                                conflicts.get(e.id))
                self.list_layout.addWidget(card)
        self.list_layout.addStretch(1)
