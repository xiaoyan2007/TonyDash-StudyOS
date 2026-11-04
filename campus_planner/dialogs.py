"""课程与考试编辑弹窗。"""
from __future__ import annotations

from datetime import date as Date

from PySide6.QtCore import QDate, Qt, QTime, Signal
from PySide6.QtGui import QDoubleValidator, QIntValidator
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QSlider, QVBoxLayout, QWidget,
)

from . import core, theme, widgets


def _field(caption: str, widget: QWidget) -> QWidget:
    box = QWidget()
    box.setStyleSheet("background: transparent;")
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    lay.addWidget(widgets.label(caption, 12))
    lay.addWidget(widget)
    return box


def _line(placeholder: str = "") -> QLineEdit:
    edit = QLineEdit()
    edit.setPlaceholderText(placeholder)
    edit.setMinimumHeight(36)
    return edit


def _grid() -> QGridLayout:
    grid = QGridLayout()
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(12)
    grid.setVerticalSpacing(10)
    grid.setColumnStretch(0, 1)
    grid.setColumnStretch(1, 1)
    return grid


class CourseDialog(widgets.GlassDialog):
    def __init__(self, parent, data: core.AppData, course: core.Course | None = None,
                 default_day: int = 1, default_period: int = 1):
        title = "编辑课程" if course else "新增课程"
        subtitle = "修改后立即同步到课表，数据只保存在本机"
        super().__init__(parent, width=566, title=title, subtitle=subtitle, icon="book")
        self.data = data
        self.course = course
        self.delete_requested = False
        self.result_course: core.Course | None = None
        self._color = course.color if course else ((len(data.courses) % 8) + 1)
        self._build(course, default_day, default_period)
        self.adjustSize()

    # -- 构建
    def _build(self, course: core.Course | None, default_day: int, default_period: int):
        total = self.data.settings.total_weeks
        periods = self.data.periods or core.default_periods()
        self.name = _line("如：高等数学 A（下）")
        self.teacher = _line("如：张伟")
        self.location = _line("如：教二-201")
        self.note = _line("可选，例如：带计算器")

        if course:
            self.name.setText(course.name)
            self.teacher.setText(course.teacher)
            self.location.setText(course.location)
            self.note.setText(course.note)

        self.day = widgets.Select()
        for i, name in enumerate(core.DAY_NAMES, start=1):
            self.day.addItem(name, i)
        self.day.setCurrentIndex((course.day if course else default_day) - 1)

        self.start = widgets.Select()
        self.end = widgets.Select()
        for i in range(1, len(periods) + 1):
            self.start.addItem(f"第 {i} 节", i)
        start_val = course.start if course else min(default_period, len(periods))
        self.start.setCurrentIndex(max(0, min(start_val, len(periods)) - 1))
        self._fill_end(course.end if course else min(start_val + 1, len(periods)))
        self.start.currentIndexChanged.connect(self._on_start_changed)

        self.time_preview = widgets.label("", 11, theme.C_SUB)
        period_row = QHBoxLayout()
        period_row.setSpacing(8)
        period_row.addWidget(self.start, 1)
        dash = widgets.label("至", 11, theme.C_SUB)
        period_row.addWidget(dash)
        period_row.addWidget(self.end, 1)
        period_row.addWidget(self.time_preview, 0)
        period_box = QWidget()
        period_box.setStyleSheet("background: transparent;")
        period_box.setLayout(period_row)
        period_row.setContentsMargins(0, 0, 0, 0)

        modes = [(m, core.WEEK_MODE_LABELS[m]) for m in core.WEEK_MODES]
        mode = course.weeks.mode if course else "all"
        self.mode = widgets.Segmented(modes, mode)
        self.weeks_edit = _line("如：1-8, 10-16")
        if course and course.weeks.mode == "custom":
            self.weeks_edit.setText(course.weeks.text)
        self.weeks_edit.setVisible(mode == "custom")
        self.mode.changed.connect(self._on_mode_changed)
        self.weeks_edit.textChanged.connect(self._refresh)

        self.hint = widgets.label("", 12)
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("background: transparent;")

        self.swatches = widgets.ColorSwatches(self._color)
        self.swatches.changed.connect(self._pick_color)

        self.preview = widgets.label("", 11.5)
        self.preview.setWordWrap(True)
        self.preview.setStyleSheet("background: transparent;")
        self.warn = widgets.label("", 12, theme.C_AMBER)
        self.warn.setWordWrap(True)
        self.warn.setStyleSheet(f"color: {theme.C_AMBER}; background: transparent;")

        grid = _grid()
        grid.addWidget(_field("课程名称 *", self.name), 0, 0, 1, 2)
        grid.addWidget(_field("老师", self.teacher), 1, 0)
        grid.addWidget(_field("地点", self.location), 1, 1)
        grid.addWidget(_field("星期", self.day), 2, 0)
        grid.addWidget(_field("节次", period_box), 2, 1)
        grid.addWidget(_field("上课周次", self.mode), 3, 0, 1, 2)
        self.weeks_box = _field("自定义周次", self.weeks_edit)
        self.weeks_box.setVisible(mode == "custom")
        grid.addWidget(self.weeks_box, 4, 0, 1, 2)
        grid.addWidget(self.hint, 5, 0, 1, 2)
        color_box = QWidget()
        color_lay = QHBoxLayout(color_box)
        color_lay.setContentsMargins(0, 0, 0, 0)
        color_lay.setSpacing(10)
        color_lay.addWidget(widgets.label("颜色", 12))
        color_lay.addWidget(self.swatches)
        color_lay.addStretch(1)
        grid.addWidget(color_box, 6, 0, 1, 2)
        grid.addWidget(_field("备注", self.note), 7, 0, 1, 2)

        self.body_layout.addLayout(grid)
        self.body_layout.addWidget(self.preview)
        self.body_layout.addWidget(self.warn)

        self.name.textChanged.connect(self._refresh)
        self.day.currentIndexChanged.connect(self._refresh)
        self.end.currentIndexChanged.connect(self._refresh)
        self.teacher.textChanged.connect(self._refresh)

        if course:
            delete = widgets.AppButton("删除课程", "trash", "danger", "md")
            delete.clicked.connect(self._delete)
            self.add_footer(delete, stretch_before=False)
            self.add_footer_stretch()
        cancel = widgets.AppButton("取消", None, "ghost", "md")
        cancel.clicked.connect(self.reject)
        save = widgets.AppButton("保存课程", "check", "primary", "md")
        save.setDefault(True)
        save.clicked.connect(self._save)
        self.add_footer(cancel)
        self.add_footer(save)
        self._refresh()

    # -- 交互
    def _fill_end(self, selected: int):
        periods = self.data.periods or core.default_periods()
        start = self.start.currentIndex() + 1
        self.end.blockSignals(True)
        self.end.clear()
        for i in range(start, len(periods) + 1):
            self.end.addItem(f"第 {i} 节", i)
        idx = max(0, min(int(selected) - start, self.end.count() - 1))
        self.end.setCurrentIndex(idx)
        self.end.blockSignals(False)

    def _on_start_changed(self):
        old = self.end.currentData() or self.start.currentIndex() + 1
        self._fill_end(max(old, self.start.currentIndex() + 1))
        self._refresh()

    def _on_mode_changed(self, key: str):
        self.weeks_box.setVisible(key == "custom")
        self.weeks_edit.setFocus()
        self._refresh()
        self.adjustSize()

    def _pick_color(self, index: int):
        self._color = index
        self._refresh()

    def _week_spec(self) -> core.WeekSpec:
        mode = self.mode.current()
        text = self.weeks_edit.text().strip() if mode == "custom" else ""
        return core.WeekSpec(mode, text)

    def _refresh(self):
        periods = self.data.periods or core.default_periods()
        total = self.data.settings.total_weeks
        start = self.start.currentIndex() + 1
        end = self.end.currentData() or start
        try:
            time_text = f"{periods[start - 1].start}–{periods[end - 1].end}"
        except Exception:
            time_text = ""
        self.time_preview.setText(time_text)
        spec = self._week_spec()
        label = core.weeks_label(spec, total)
        weeks = core.expand_weeks(spec, total)
        if spec.mode == "custom" and not weeks:
            self.hint.setText("请输入周次，例如 1-8, 10-16")
            self.hint.setStyleSheet(f"color: {theme.C_RED}; background: transparent;")
        else:
            self.hint.setText(f"共 {len(weeks)} 个教学周 · {label}")
            self.hint.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        self.preview.setText(
            f"<span style='color:{theme.C_TEXT};'>"
            f"{core.DAY_NAMES[self.day.currentIndex()]} 第 {start}–{end} 节"
            f"</span><span style='color:{theme.C_SUB};'> · {time_text} · {label}</span>"
        )
        conflicts = []
        name = self.name.text().strip()
        if name:
            candidate = core.Course(
                id=self.course.id if self.course else "tmp",
                name=name,
                teacher=self.teacher.text().strip(),
                location=self.location.text().strip(),
                day=self.day.currentIndex() + 1,
                start=start,
                end=end,
                weeks=spec,
                color=self._color,
            )
            conflicts = core.course_conflicts(self.data.courses, candidate, total)
        if conflicts:
            other, weeks = conflicts[0]
            extra = f" 等 {len(conflicts)} 门" if len(conflicts) > 1 else ""
            self.warn.setText(
                f"与「{other.name}」在第 {core.compress_ranges(weeks)} 周时间冲突{extra}，仍可保存。"
            )
        else:
            self.warn.setText("")

    # -- 保存
    def _save(self):
        name = self.name.text().strip()
        if not name:
            self.show_error("请填写课程名称")
            self.name.setFocus()
            return
        spec = self._week_spec()
        if spec.mode == "custom":
            weeks = core.parse_weeks_text(spec.text, self.data.settings.total_weeks)
            if not weeks:
                self.show_error("自定义周次为空或格式不正确，例如：1-8, 10-16")
                self.weeks_edit.setFocus()
                return
        periods = self.data.periods or core.default_periods()
        start = self.start.currentIndex() + 1
        end = min(self.end.currentData() or start, len(periods))
        if start > end:
            start, end = end, start
        course = self.course or core.Course(id=core.new_id("c"), name=name)
        course.name = name
        course.teacher = self.teacher.text().strip()
        course.location = self.location.text().strip()
        course.day = self.day.currentIndex() + 1
        course.start = start
        course.end = end
        course.weeks = spec
        course.color = self._color
        course.note = self.note.text().strip()
        self.result_course = course
        self.accept()

    def _delete(self):
        self.delete_requested = True
        self.accept()


class CustomRow(QWidget):
    removed = Signal(object)

    def __init__(self, label: str = "", value: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(7)
        self.label_edit = QLineEdit(label)
        self.label_edit.setPlaceholderText("字段名，如 座位号")
        self.value_edit = QLineEdit(value)
        self.value_edit.setPlaceholderText("内容")
        for edit in (self.label_edit, self.value_edit):
            edit.setMinimumHeight(34)
        self.label_edit.setMaximumWidth(150)
        remove = widgets.AppButton("", "close", "ghost", "icon")
        remove.setToolTip("移除字段")
        remove.clicked.connect(lambda: self.removed.emit(self))
        lay.addWidget(self.label_edit)
        lay.addWidget(self.value_edit, 1)
        lay.addWidget(remove)


class ExamDialog(widgets.GlassDialog):
    def __init__(self, parent, data: core.AppData, exam: core.Exam | None = None):
        title = "编辑考试" if exam else "新增考试"
        subtitle = "记录考试时间、地点与复习进度，支持自定义字段"
        super().__init__(parent, width=590, title=title, subtitle=subtitle, icon="report")
        self.data = data
        self.exam = exam
        self.delete_requested = False
        self.result_exam: core.Exam | None = None
        self._color = exam.color if exam else ((len(data.exams) % 8) + 1)
        self._custom_rows: list[CustomRow] = []
        self._build(exam)
        self.adjustSize()

    def _build(self, exam: core.Exam | None):
        self.name = _line("如：高等数学 A（下）")
        self.type = widgets.Select()
        self.type.setEditable(True)
        self.type.addItems(self.data.exam_types or core.DEFAULT_EXAM_TYPES)
        self.type.setCurrentText(exam.type if exam else "闭卷")
        self.credits = _line("如：4")
        self.credits.setValidator(QDoubleValidator(0.0, 30.0, 1))
        self.date = widgets.DateField()
        if exam and exam.date_obj():
            d0 = exam.date_obj()
        else:
            d0 = Date.today() + __import__("datetime").timedelta(days=14)
        self.date.setDate(QDate(d0.year, d0.month, d0.day))
        self.time = widgets.TimeField()
        if exam:
            self.time.setTime(QTime(int(exam.start_time[:2]), int(exam.start_time[3:5])))
        else:
            self.time.setTime(QTime(9, 0))
        self.duration = _line("120")
        self.duration.setValidator(QIntValidator(10, 600))
        self.duration.setText(str(exam.duration if exam else 120))
        self.location = _line("如：教二-201")
        self.seat = _line("如：A-12")
        self.note = _line("可选，例如：可带一张 A4 纸")
        self.credits.setText(("%g" % exam.credits) if exam and exam.credits else ("4" if not exam else ""))
        if exam:
            self.name.setText(exam.name)
            self.location.setText(exam.location)
            self.seat.setText(exam.seat)
            self.note.setText(exam.note)

        self.progress = QSlider(Qt.Orientation.Horizontal)
        self.progress.setRange(0, 100)
        self.progress.setValue(exam.progress if exam else 0)
        self.progress_value = widgets.label("0%", 11, theme.C_BLUE)
        self.progress.valueChanged.connect(
            lambda v: self.progress_value.setText(f"{v}%")
        )
        self.progress_value.setText(f"{self.progress.value()}%")
        progress_row = QHBoxLayout()
        progress_row.setContentsMargins(0, 0, 0, 0)
        progress_row.setSpacing(10)
        progress_row.addWidget(self.progress, 1)
        progress_row.addWidget(self.progress_value, 0)
        progress_box = QWidget()
        progress_box.setLayout(progress_row)
        progress_box.setStyleSheet("background: transparent;")

        self.swatches = widgets.ColorSwatches(self._color)
        self.swatches.changed.connect(self._pick_color)

        grid = _grid()
        grid.addWidget(_field("考试科目 *", self.name), 0, 0, 1, 2)
        grid.addWidget(_field("类型", self.type), 1, 0)
        grid.addWidget(_field("学分", self.credits), 1, 1)
        grid.addWidget(_field("日期 *", self.date), 2, 0)
        grid.addWidget(_field("开始时间 *", self.time), 2, 1)
        grid.addWidget(_field("时长（分钟）", self.duration), 3, 0)
        grid.addWidget(_field("地点", self.location), 3, 1)
        grid.addWidget(_field("座位", self.seat), 4, 0)
        grid.addWidget(_field("复习进度", progress_box), 4, 1)
        grid.addWidget(_field("备注", self.note), 5, 0, 1, 2)
        self.body_layout.addLayout(grid)

        custom_head = QHBoxLayout()
        custom_head.setContentsMargins(0, 0, 0, 0)
        custom_head.addWidget(widgets.label("自定义字段", 12))
        custom_head.addStretch(1)
        add = widgets.AppButton("添加字段", "plus", "soft", "sm")
        add.clicked.connect(lambda: self._add_custom("", ""))
        custom_head.addWidget(add)
        self.body_layout.addLayout(custom_head)
        self.custom_box = QVBoxLayout()
        self.custom_box.setContentsMargins(0, 0, 0, 0)
        self.custom_box.setSpacing(7)
        self.body_layout.addLayout(self.custom_box)
        if exam and exam.custom:
            for f in exam.custom:
                self._add_custom(f.label, f.value)

        color_box = QWidget()
        color_lay = QHBoxLayout(color_box)
        color_lay.setContentsMargins(0, 0, 0, 0)
        color_lay.setSpacing(10)
        color_lay.addWidget(widgets.label("颜色", 12))
        color_lay.addWidget(self.swatches)
        color_lay.addStretch(1)
        self.body_layout.addWidget(color_box)

        self.preview = widgets.label("", 11.5)
        self.preview.setWordWrap(True)
        self.preview.setStyleSheet("background: transparent;")
        self.warn = widgets.label("", 12, theme.C_AMBER)
        self.warn.setWordWrap(True)
        self.warn.setStyleSheet(f"color: {theme.C_AMBER}; background: transparent;")
        self.body_layout.addWidget(self.preview)
        self.body_layout.addWidget(self.warn)

        for widget in (self.name, self.credits, self.duration, self.location):
            widget.textChanged.connect(self._refresh)
        self.date.dateChanged.connect(self._refresh)
        self.time.timeChanged.connect(self._refresh)
        self.type.currentTextChanged.connect(self._refresh)
        self.progress.valueChanged.connect(self._refresh)

        if exam:
            delete = widgets.AppButton("删除考试", "trash", "danger", "md")
            delete.clicked.connect(self._delete)
            self.add_footer(delete, stretch_before=False)
            self.add_footer_stretch()
        cancel = widgets.AppButton("取消", None, "ghost", "md")
        cancel.clicked.connect(self.reject)
        save = widgets.AppButton("保存考试", "check", "primary", "md")
        save.setDefault(True)
        save.clicked.connect(self._save)
        self.add_footer(cancel)
        self.add_footer(save)
        self._refresh()

    def _add_custom(self, label: str, value: str):
        if len(self._custom_rows) >= 6:
            self.show_error("自定义字段最多 6 条")
            return
        row = CustomRow(label, value, self)
        row.removed.connect(self._remove_custom)
        self._custom_rows.append(row)
        self.custom_box.addWidget(row)

    def _remove_custom(self, row: CustomRow):
        if row in self._custom_rows:
            self._custom_rows.remove(row)
        row.setParent(None)
        row.deleteLater()

    def _pick_color(self, index: int):
        self._color = index
        self._refresh()

    def _duration_minutes(self) -> int:
        try:
            return max(10, min(600, int(self.duration.text().strip() or "120")))
        except ValueError:
            return 120

    def _refresh(self):
        try:
            credits = float(self.credits.text().strip() or "0")
        except ValueError:
            credits = 0.0
        d = self.date.date()
        date_obj = Date(d.year(), d.month(), d.day())
        t = self.time.time()
        start = f"{t.hour():02d}:{t.minute():02d}"
        minutes = self._duration_minutes()
        end_min = core.time_to_minutes(start) + minutes
        end = core.minutes_to_time(min(end_min, 23 * 60 + 59))
        delta = core.days_until(date_obj)
        rel = core.relative_day_text(date_obj) if delta >= 0 else f"{abs(delta)} 天前"
        self.preview.setText(
            f"<span style='color:{theme.C_TEXT};'>{core.format_cn_date(date_obj)} "
            f"{core.format_weekday(date_obj)}</span>"
            f"<span style='color:{theme.C_SUB};'> · {start}–{end} · {minutes} 分钟 · "
            f"{credits:g} 学分 · {rel}</span>"
        )
        warnings = []
        candidate = core.Exam(
            id=self.exam.id if self.exam else "tmp",
            name=self.name.text().strip(),
            type=self.type.currentText().strip(),
            credits=credits,
            date=date_obj.isoformat(),
            start_time=start,
            duration=minutes,
            location=self.location.text().strip(),
            seat=self.seat.text().strip(),
            progress=self.progress.value(),
            color=self._color,
        )
        if self.name.text().strip():
            others = core.exam_conflicts(self.data.exams, candidate)
            if others:
                warnings.append(f"与「{others[0].name}」时间重叠")
            classes = core.exam_class_conflicts(candidate, self.data)
            if classes:
                warnings.append(f"当天有课：{'、'.join(c.name for c in classes[:2])}")
        if not self.location.text().strip():
            warnings.append("还没填考试地点")
        self.warn.setText(" · ".join(warnings))

    def _save(self):
        name = self.name.text().strip()
        if not name:
            self.show_error("请填写考试科目")
            self.name.setFocus()
            return
        d = self.date.date()
        date_obj = Date(d.year(), d.month(), d.day())
        t = self.time.time()
        start = f"{t.hour():02d}:{t.minute():02d}"
        try:
            credits = float(self.credits.text().strip() or "0")
        except ValueError:
            self.show_error("学分请填写数字")
            return
        exam = self.exam or core.Exam(id=core.new_id("e"), name=name)
        exam.name = name
        exam.type = self.type.currentText().strip() or "闭卷"
        exam.credits = max(0.0, min(30.0, credits))
        exam.date = date_obj.isoformat()
        exam.start_time = start
        exam.duration = self._duration_minutes()
        exam.location = self.location.text().strip()
        exam.seat = self.seat.text().strip()
        exam.progress = self.progress.value()
        exam.note = self.note.text().strip()
        exam.color = self._color
        exam.custom = [
            core.CustomField(row.label_edit.text().strip(), row.value_edit.text().strip())
            for row in self._custom_rows
            if row.label_edit.text().strip() or row.value_edit.text().strip()
        ]
        if exam.type not in self.data.exam_types:
            self.data.exam_types.append(exam.type)
        self.result_exam = exam
        self.accept()

    def _delete(self):
        self.delete_requested = True
        self.accept()
