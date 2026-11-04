"""课程表页面：星期 × 节次网格，点击空白新增、点击课程编辑。"""
from __future__ import annotations

from datetime import date as Date, datetime

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from .. import core, theme, widgets
from . import common

LEFT = 76
HEAD = 46
ROW_H = 66


class TimetableWidget(QWidget):
    course_clicked = Signal(object)
    slot_clicked = Signal(int, int)

    def __init__(self, parent=None, show_head: bool = True):
        super().__init__(parent)
        self.show_head = show_head
        self._y0 = HEAD if show_head else 0
        self.data: core.AppData | None = None
        self.week = 1
        self.search = ""
        self.days: list[int] = list(range(1, 8))
        self.hover: tuple[int, int] | None = None
        self.setMouseTracking(True)
        self.setStyleSheet("background: transparent;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    # -- 尺寸
    def _rows(self) -> int:
        return len(self.data.periods) if self.data else 12

    def _min_width(self) -> int:
        return LEFT + len(self.days) * 112

    def sizeHint(self) -> QSize:
        return QSize(self._min_width(), self._y0 + self._rows() * ROW_H + 6)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def set_view(self, data: core.AppData, week: int, search: str):
        self.data = data
        self.week = week
        self.search = search
        self.days = list(range(1, 8)) if data.settings.show_weekend else list(range(1, 6))
        self.setMinimumSize(self._min_width(), self._y0 + self._rows() * ROW_H + 6)
        self.updateGeometry()
        self.update()

    # -- 几何
    def _col_width(self) -> float:
        return max(60.0, (self.width() - LEFT) / max(1, len(self.days)))

    def _cell(self, pos) -> tuple[int, int] | None:
        if not self.data:
            return None
        x, y = pos.x(), pos.y()
        if x < LEFT or y < self._y0:
            return None
        col = int((x - LEFT) // self._col_width())
        row = int((y - self._y0) // ROW_H)
        if 0 <= col < len(self.days) and 0 <= row < self._rows():
            return self.days[col], row + 1
        return None

    def _course_rect(self, course: core.Course) -> QRectF:
        col = self.days.index(course.day)
        x = LEFT + col * self._col_width()
        y = self._y0 + (course.start - 1) * ROW_H
        return QRectF(x + 2, y + 2, self._col_width() - 4,
                      (course.end - course.start + 1) * ROW_H - 4)

    def _course_at(self, pos) -> core.Course | None:
        if not self.data:
            return None
        for course in sorted(self.data.courses, key=lambda c: c.start, reverse=True):
            if course.day not in self.days:
                continue
            if not core.course_in_week(course, self.week, self.data.settings.total_weeks):
                continue
            if self._course_rect(course).contains(pos):
                return course
        return None

    def _matches(self, course: core.Course) -> bool:
        if not self.search:
            return True
        q = self.search.lower()
        return any(q in (text or "").lower() for text in
                   (course.name, course.teacher, course.location, course.note))

    # -- 事件
    def mouseMoveEvent(self, event):
        over = self._course_at(event.position())
        cell = None if over else self._cell(event.position())
        if cell != self.hover:
            self.hover = cell
            self.update()
        self.setCursor(Qt.CursorShape.PointingHandCursor
                       if (over or cell) else Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.hover = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            course = self._course_at(event.position())
            if course:
                self.course_clicked.emit(course)
                return
            cell = self._cell(event.position())
            if cell:
                self.slot_clicked.emit(*cell)
                return
        super().mousePressEvent(event)

    # -- 绘制
    def paintEvent(self, event):
        if not self.data:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        settings = self.data.settings
        rows = self._rows()
        colw = self._col_width()
        today = Date.today()
        total_w = LEFT + colw * len(self.days)
        total_h = self._y0 + rows * ROW_H

        dark = theme.MODE == "dark"
        p.fillRect(QRectF(0, 0, total_w, total_h),
                   QColor(255, 255, 255, 16) if dark else QColor(255, 255, 255, 92))

        # 今天列
        for idx, day in enumerate(self.days):
            d = core.date_of_week_day(settings.term_start, self.week, day)
            if d == today:
                p.fillRect(QRectF(LEFT + idx * colw, 0, colw, total_h),
                           QColor(10, 132, 255, 20))

        # 节次列
        for i in range(rows):
            y = self._y0 + i * ROW_H
            period = self.data.periods[i]
            p.setFont(theme.font(11.5, theme.QFont.Weight.DemiBold))
            p.setPen(QColor(theme.C_SUB))
            p.drawText(QRectF(7, y + 5, LEFT - 13, 15), Qt.AlignmentFlag.AlignLeft,
                       f"第 {i + 1} 节")
            p.setFont(theme.font(11.5, theme.QFont.Weight.DemiBold))
            p.setPen(QColor(theme.C_TEXT))
            p.drawText(QRectF(7, y + 22, LEFT - 13, 16), Qt.AlignmentFlag.AlignLeft,
                       period.start)
            p.setFont(theme.font(11.5))
            p.setPen(QColor(theme.C_SUB))
            p.drawText(QRectF(7, y + 39, LEFT - 13, 15), Qt.AlignmentFlag.AlignLeft,
                       period.end)

        # 网格线
        p.setPen(QPen(QColor(255, 255, 255, 30) if dark else QColor(28, 28, 30, 22), 1))
        for i in range(rows + 1):
            y = self._y0 + i * ROW_H
            p.drawLine(int(0), int(y), int(total_w), int(y))
        for idx in range(len(self.days) + 1):
            x = LEFT + idx * colw
            p.drawLine(int(x), int(0), int(x), int(total_h))
        p.drawLine(int(LEFT), int(0), int(LEFT), int(total_h))

        # 悬停空格
        if self.hover and not self.search:
            day, period = self.hover
            if day in self.days:
                col = self.days.index(day)
                rect = QRectF(LEFT + col * colw + 2, self._y0 + (period - 1) * ROW_H + 2,
                              colw - 4, ROW_H - 4)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(10, 132, 255, 14))
                p.drawRoundedRect(rect, 9, 9)
                p.setFont(theme.icon_font(13))
                p.setPen(QColor(10, 132, 255, 120))
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, theme.icon_char("plus"))

        # 课程块
        conflicts = core.conflicts_map(self.data.courses, settings.total_weeks)
        for course in self.data.courses:
            if course.day not in self.days:
                continue
            if not core.course_in_week(course, self.week, settings.total_weeks):
                continue
            rect = self._course_rect(course)
            matched = self._matches(course)
            p.setOpacity(0.30 if (self.search and not matched) else 1.0)
            base = QColor(theme.course_color(course.color))
            # 先铺一层近乎不透明的底色，避免课表网格线从半透明课程块里透出来割断文字。
            # 深色模式下必须用深底 + 亮色文字，否则白底白字完全看不见。
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(30, 35, 50, 246) if dark else QColor(255, 255, 255, 236))
            p.drawRoundedRect(rect, 10, 10)
            fill = QColor(base)
            fill.setAlpha(58 if dark else 44)
            border = QColor(base)
            border.setAlpha(150 if dark else 112)
            p.setPen(QPen(border, 1))
            p.setBrush(fill)
            p.drawRoundedRect(rect, 10, 10)
            bar = QColor(base)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bar)
            p.drawRoundedRect(QRectF(rect.left() + 1, rect.top() + 7, 3.4,
                                     max(10.0, rect.height() - 14)), 1.7, 1.7)
            text_x = rect.left() + 11
            text_w = rect.width() - 20
            tall = rect.height() >= 108
            fm_name = QFontMetrics(theme.font(13, theme.QFont.Weight.DemiBold))
            p.setFont(theme.font(13, theme.QFont.Weight.DemiBold))
            p.setPen(QColor(theme.C_TEXT))
            if tall:
                p.drawText(QRectF(text_x, rect.top() + 7, text_w, 33),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
                           | Qt.TextFlag.TextWordWrap, course.name)
            else:
                p.drawText(QRectF(text_x, rect.top() + 7, text_w, 18),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                           fm_name.elidedText(course.name, Qt.TextElideMode.ElideRight,
                                              int(text_w)))
            meta = " · ".join(t for t in (course.teacher, course.location) if t)
            if meta:
                fm_meta = QFontMetrics(theme.font(11.5))
                p.setFont(theme.font(11.5))
                p.setPen(QColor(theme.C_SUB))
                p.drawText(QRectF(text_x, rect.top() + (40 if tall else 25), text_w, 15),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                           fm_meta.elidedText(meta, Qt.TextElideMode.ElideRight, int(text_w)))
            fm_w = QFontMetrics(theme.font(11))
            p.setFont(theme.font(11))
            p.setPen(QColor(theme.C_SUB))
            p.drawText(QRectF(text_x, rect.bottom() - 17, text_w, 14),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       fm_w.elidedText(core.weeks_label(course.weeks, settings.total_weeks),
                                       Qt.TextElideMode.ElideRight, int(text_w)))
            if conflicts.get(course.id):
                p.setPen(QPen(QColor("#FFFFFF"), 1.4))
                p.setBrush(QColor(theme.C_RED))
                p.drawEllipse(QRectF(rect.right() - 10, rect.top() + 6, 6.4, 6.4))
            p.setOpacity(1.0)
        p.end()



class TimetableHeader(QWidget):
    """固定在滚动区上方的星期表头，横向偏移与课表主体同步。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data: core.AppData | None = None
        self.week = 1
        self.days: list[int] = list(range(1, 8))
        self.offset = 0
        self.content_width = 0
        self.setFixedHeight(HEAD)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("background: transparent;")

    def set_view(self, data: core.AppData, week: int):
        self.data = data
        self.week = week
        self.days = list(range(1, 8)) if data.settings.show_weekend else list(range(1, 6))
        self.update()

    def set_content_width(self, width: int):
        if width > 0 and width != self.content_width:
            self.content_width = width
            self.update()

    def set_offset(self, value: int):
        if value != self.offset:
            self.offset = value
            self.update()

    def paintEvent(self, event):
        if not self.data:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        content_w = self.content_width or self.width()
        colw = max(60.0, (content_w - LEFT) / max(1, len(self.days)))
        today = Date.today()
        p.save()
        p.translate(-self.offset, 0)

        for idx, day in enumerate(self.days):
            d = core.date_of_week_day(self.data.settings.term_start, self.week, day)
            if d == today:
                p.fillRect(QRectF(LEFT + idx * colw, 0, colw, HEAD),
                           QColor(10, 132, 255, 20))

        p.setFont(theme.font(11.5))
        p.setPen(QColor(theme.C_SUB))
        p.drawText(QRectF(8, 0, LEFT - 14, HEAD),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "节次")

        for idx, day in enumerate(self.days):
            d = core.date_of_week_day(self.data.settings.term_start, self.week, day)
            x = LEFT + idx * colw
            is_today = d == today
            p.setFont(theme.font(11, theme.QFont.Weight.DemiBold))
            p.setPen(QColor(theme.C_BLUE if is_today else theme.C_TEXT))
            p.drawText(QRectF(x, 5, colw, 20), Qt.AlignmentFlag.AlignCenter,
                       core.DAY_NAMES[day - 1])
            if is_today:
                pill = QRectF(x + colw / 2 - 16, 25, 32, 18)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(theme.C_BLUE))
                p.drawRoundedRect(pill, 9, 9)
                p.setPen(QColor("#FFFFFF"))
            else:
                p.setPen(QColor(theme.C_SUB))
            p.setFont(theme.font(12, theme.QFont.Weight.DemiBold
                                 if is_today else theme.QFont.Weight.Normal))
            p.drawText(QRectF(x, 24, colw, 18), Qt.AlignmentFlag.AlignCenter, str(d.day))

        _line = QColor(255, 255, 255, 30) if theme.MODE == "dark" else QColor(28, 28, 30, 22)
        p.setPen(QPen(_line, 1))
        p.drawLine(0, HEAD - 1, content_w, HEAD - 1)
        p.setPen(QPen(_line, 1))
        for idx in range(len(self.days) + 1):
            x = LEFT + idx * colw
            p.drawLine(int(x), 0, int(x), HEAD)
        p.drawLine(int(LEFT), 0, int(LEFT), HEAD)
        p.restore()
        p.end()


class SchedulePage(QWidget):
    week_changed = Signal(int)
    new_course = Signal(object)
    edit_course = Signal(object)
    sample_action = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self.data: core.AppData | None = None
        self.week = 1
        self.search = ""
        self._week_syncing = False
        self._build()

    # -- 构建
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        self.header = common.PageHeader("", "课程表", hint="点空白格子新建课程，点课程块可编辑；← → 换周")
        add = widgets.AppButton("新增课程", "plus", "primary", "md")
        add.clicked.connect(lambda: self.new_course.emit(None))
        self.header.add_action(add)
        root.addWidget(self.header)

        bar_card = widgets.GlassCard(radius=12, alpha=128)
        bar_wrap = QHBoxLayout(bar_card)
        bar_wrap.setContentsMargins(8, 5, 8, 5)
        bar_wrap.setSpacing(0)
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(8)
        prev = widgets.AppButton("", "left", "ghost", "icon")
        prev.setToolTip("上一周")
        prev.clicked.connect(lambda: self._step_week(-1))
        self.week_select = widgets.Select()
        self.week_select.setMinimumWidth(138)
        self.week_select.setMaximumWidth(158)
        self.week_select.currentIndexChanged.connect(self._on_week_select)
        nxt = widgets.AppButton("", "right", "ghost", "icon")
        nxt.setToolTip("下一周")
        nxt.clicked.connect(lambda: self._step_week(1))
        today_btn = widgets.AppButton("本周", None, "soft", "sm")
        today_btn.clicked.connect(self._goto_today)
        self.range_label = widgets.label("", 11.5, theme.C_SUB)
        self.search_box = widgets.SearchBox("搜索课程、老师、地点")
        self.search_box.setMinimumWidth(220)
        self.search_box.setMaximumWidth(280)
        self.search_box.textChanged.connect(self._on_search)
        self.count_chip = widgets.Chip("本周 0 门", "accent")
        self.conflict_btn = widgets.AppButton("冲突", "warning", "ghost", "sm")
        self.conflict_btn.hide()
        self.conflict_btn.clicked.connect(self._show_conflicts)
        bar.addWidget(prev)
        bar.addWidget(self.week_select)
        bar.addWidget(nxt)
        bar.addWidget(today_btn)
        bar.addWidget(self.range_label)
        bar.addStretch(1)
        bar.addWidget(self.search_box)
        bar.addWidget(self.count_chip)
        bar.addWidget(self.conflict_btn)
        bar_wrap.addLayout(bar)
        root.addWidget(bar_card)

        self.banner = widgets.GlassCard(radius=14, alpha=170)
        self.banner_layout = QHBoxLayout(self.banner)
        self.banner_layout.setContentsMargins(14, 10, 12, 10)
        self.banner_layout.setSpacing(9)
        self.banner.hide()
        root.addWidget(self.banner)

        grid_card = widgets.GlassCard(radius=16, alpha=150)
        grid_lay = QVBoxLayout(grid_card)
        grid_lay.setContentsMargins(10, 8, 10, 10)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.timetable = TimetableWidget(show_head=False)
        self.timetable.course_clicked.connect(self.edit_course)
        self.timetable.slot_clicked.connect(self._on_slot)
        self.scroll.setWidget(self.timetable)
        self.header_row = TimetableHeader()
        self.scroll.horizontalScrollBar().valueChanged.connect(self.header_row.set_offset)
        grid_lay.setSpacing(0)
        grid_lay.addWidget(self.header_row)
        grid_lay.addWidget(self.scroll, 1)
        self.empty_panel = QWidget()
        self.empty_panel.setStyleSheet("background: transparent;")
        ep = QVBoxLayout(self.empty_panel)
        ep.setContentsMargins(0, 0, 0, 0)
        ep.setSpacing(0)
        empty_add = widgets.AppButton("新增第一门课程", "plus", "primary", "lg")
        empty_add.clicked.connect(lambda: self.new_course.emit(None))
        self.empty_state = widgets.EmptyState(
            "calendar", "还没有课程",
            "把课程名称、老师、节次和周次填进来，课表就会自动排好。",
            action=empty_add,
        )
        ep.addWidget(self.empty_state)
        grid_lay.addWidget(self.empty_panel, 1)
        self.empty_panel.hide()
        root.addWidget(grid_card, 1)


    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_header_width()

    def _sync_header_width(self):
        if not hasattr(self, "header_row"):
            return
        self.header_row.set_content_width(max(self.timetable.width(),
                                              self.scroll.viewport().width()))
        self.header_row.set_offset(self.scroll.horizontalScrollBar().value())

    # -- 数据
    def set_data(self, data: core.AppData, week: int):
        self.data = data
        self.week = max(1, min(int(week), data.settings.total_weeks))
        if not self.search and self.search_box.text():
            self.search = self.search_box.text()
        self._sync_weeks()
        self.timetable.set_view(data, self.week, self.search)
        self.header_row.set_view(data, self.week)
        self._sync_header_width()
        self._update_texts()
        self._update_banner()

    def _sync_weeks(self):
        if not self.data:
            return
        total = self.data.settings.total_weeks
        if self.week_select.count() != total:
            self._week_syncing = True
            self.week_select.blockSignals(True)
            self.week_select.clear()
            for i in range(1, total + 1):
                self.week_select.addItem(f"第 {i} 周", i)
            self.week_select.blockSignals(False)
            self._week_syncing = False
        self.week_select.blockSignals(True)
        self.week_select.setCurrentIndex(self.week - 1)
        self.week_select.blockSignals(False)

    def _update_texts(self):
        if not self.data:
            return
        s = self.data.settings
        self.header.set_eyebrow(f"{s.term_name} · 第 {self.week} / {s.total_weeks} 周")
        d1 = core.date_of_week_day(s.term_start, self.week, 1)
        d2 = core.date_of_week_day(s.term_start, self.week, 7)
        self.range_label.setText(core.format_short_range(d1, d2))
        self.header.set_subtitle(self._today_text())
        visible = [c for c in self.data.courses
                   if c.day in self.timetable.days
                   and core.course_in_week(c, self.week, s.total_weeks)]
        self.count_chip.setText(f"本周 {len(visible)} 门")
        conflict_count = sum(1 for c in self.data.courses
                             if core.course_conflicts(self.data.courses, c, s.total_weeks))
        if conflict_count:
            self.conflict_btn.setText(f"冲突 {conflict_count} 处")
            self.conflict_btn.show()
        else:
            self.conflict_btn.hide()

    def _today_text(self) -> str:
        if not self.data:
            return ""
        today = Date.today()
        day = today.isoweekday()
        week = core.current_week(self.data.settings.term_start, self.data.settings.total_weeks)
        courses = [c for c in self.data.courses
                   if c.day == day and core.course_in_week(c, week, self.data.settings.total_weeks)]
        if not self.data.settings.show_weekend and day > 5:
            return "今天没有课，周末愉快"
        if not courses:
            return "今天没有课，可以安排自习或复习"
        courses.sort(key=lambda c: c.start)
        now = datetime.now()
        current_min = now.hour * 60 + now.minute
        upcoming = None
        for c in courses:
            try:
                start = core.time_to_minutes(self.data.periods[c.start - 1].start)
            except Exception:
                continue
            if start >= current_min:
                upcoming = c
                break
        text = f"今天 {len(courses)} 门课"
        if upcoming:
            try:
                start_text = self.data.periods[upcoming.start - 1].start
            except Exception:
                start_text = ""
            text += f" · 下一门 {start_text} {upcoming.name}"
        else:
            text += " · 今天的课已结束"
        return text

    def _update_banner(self):
        if not self.data:
            return
        while self.banner_layout.count():
            item = self.banner_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not self.data.courses:
            self.banner.hide()
            self.scroll.hide()
            self.empty_panel.show()
        else:
            self.banner.hide()
            self.empty_panel.hide()
            self.scroll.show()

    # -- 交互
    def _on_search(self, text: str):
        self.search = text.strip()
        if self.data:
            self.timetable.set_view(self.data, self.week, self.search)

    def _on_week_select(self, index: int):
        if self._week_syncing or index < 0:
            return
        self.week_changed.emit(index + 1)

    def _step_week(self, delta: int):
        if not self.data:
            return
        target = max(1, min(self.data.settings.total_weeks, self.week + delta))
        if target != self.week:
            self.week_changed.emit(target)

    def _goto_today(self):
        if not self.data:
            return
        week = core.current_week(self.data.settings.term_start, self.data.settings.total_weeks)
        if week != self.week:
            self.week_changed.emit(week)
        else:
            self.timetable.set_view(self.data, self.week, self.search)

    def _on_slot(self, day: int, period: int):
        self.new_course.emit({"day": day, "period": period})

    def show_conflict_marks(self):
        self._show_conflicts()

    def _show_conflicts(self):
        if not self.data:
            return
        total = self.data.settings.total_weeks
        rows = []
        for course in self.data.courses:
            for other, weeks in core.course_conflicts(self.data.courses, course, total):
                if course.id < other.id:
                    rows.append((course, other, weeks))
        dlg = widgets.GlassDialog(self.window(), width=520, title="时间冲突",
                                  subtitle="同一时段、同一周次出现了多门课程", icon="warning")
        if not rows:
            dlg.body_layout.addWidget(widgets.label("没有冲突，课表很干净。", 12, theme.C_TEXT))
        else:
            for course, other, weeks in rows[:8]:
                line = widgets.label(
                    f"{course.name} × {other.name}\n"
                    f"{core.DAY_NAMES[course.day - 1]} 第 {course.start}–{course.end} 节 · "
                    f"第 {core.compress_ranges(weeks)} 周",
                    11, theme.C_TEXT)
                line.setWordWrap(True)
                dlg.body_layout.addWidget(line)
        close = widgets.AppButton("知道了", None, "primary", "md")
        close.clicked.connect(dlg.accept)
        dlg.add_footer(close)
        dlg.exec()
