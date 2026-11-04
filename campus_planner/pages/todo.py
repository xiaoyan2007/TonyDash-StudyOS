"""待办页面：每日 / 每周 / 一次性待办，完成统计与完成历史。"""
from __future__ import annotations

import math
import random
from datetime import date as Date, datetime, timedelta

from PySide6.QtCore import (
    QDate, QEasingCurve, QPointF, QRectF, Qt, QTimer, QVariantAnimation, Signal,
)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QMenu, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

from .. import core, theme, widgets
from ..about_dialogs import TaskHistoryDialog
from . import common


class TaskCheck(QWidget):
    toggled = Signal(bool)

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self._checked = checked
        self._hover = False
        self._pop = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(320)
        self._anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self._anim.valueChanged.connect(self._on_pop)
        self.setFixedSize(24, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("标记完成 / 未完成")

    def setChecked(self, value: bool):
        self._checked = bool(value)
        self.update()

    def _on_pop(self, value):
        self._pop = float(value)
        self.update()

    def isChecked(self) -> bool:
        return self._checked

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._checked = not self._checked
            if self._checked:
                self._anim.stop()
                self._anim.setStartValue(0.0)
                self._anim.setEndValue(1.0)
                self._anim.start()
            self.update()
            self.toggled.emit(self._checked)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        if self._checked and self._pop > 0:
            p.setPen(Qt.PenStyle.NoPen)
            glow = QColor(theme.C_GREEN)
            glow.setAlphaF(0.20 * (1.0 - abs(self._pop - 0.5) * 2))
            p.setBrush(glow)
            p.drawEllipse(box.adjusted(-2, -2, 2, 2))
        if self._checked:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(theme.C_GREEN))
            p.drawRoundedRect(box, 6, 6)
            p.setPen(QPen(QColor("#FFFFFF"), 2.1,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                          Qt.PenJoinStyle.RoundJoin))
            x, y, w, h = box.x(), box.y(), box.width(), box.height()
            p.drawLine(int(x + w * 0.24), int(y + h * 0.52),
                       int(x + w * 0.43), int(y + h * 0.71))
            p.drawLine(int(x + w * 0.43), int(y + h * 0.71),
                       int(x + w * 0.77), int(y + h * 0.30))
        else:
            p.setPen(QPen(QColor(theme.C_SUB if self._hover else "#B9BDC6"), 1.6))
            p.setBrush(QColor(255, 255, 255, 120))
            p.drawRoundedRect(box, 6, 6)
        p.end()


class ClickableLabel(QLabel):
    clicked = Signal()

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class ConfettiOverlay(QWidget):
    """完成待办时的小范围彩色纸屑动画。"""

    COLORS = ("#34C759", "#0A84FF", "#FF9F0A", "#FF375F", "#BF5AF2", "#30B0C7")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._parts: list[dict] = []
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._step)
        self.hide()

    def burst(self, pos: QPointF):
        self.setGeometry(self.parentWidget().rect())
        self.raise_()
        self.show()
        for i in range(16):
            ang = random.uniform(-math.pi * 0.95, -math.pi * 0.05)
            speed = random.uniform(2.2, 5.6)
            self._parts.append({
                "x": pos.x(), "y": pos.y(),
                "vx": math.cos(ang) * speed * random.uniform(0.8, 1.5),
                "vy": math.sin(ang) * speed,
                "life": 1.0,
                "size": random.uniform(3.0, 5.8),
                "color": QColor(random.choice(self.COLORS)),
            })
        if not self._timer.isActive():
            self._timer.start()

    def _step(self):
        alive = []
        for p in self._parts:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vy"] += 0.24
            p["vx"] *= 0.985
            p["life"] -= 0.022
            if p["life"] > 0:
                alive.append(p)
        self._parts = alive
        if not self._parts:
            self._timer.stop()
            self.hide()
        self.update()

    def paintEvent(self, event):
        if not self._parts:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for part in self._parts:
            c = QColor(part["color"])
            c.setAlphaF(max(0.0, min(1.0, part["life"])))
            p.setBrush(c)
            p.setPen(Qt.PenStyle.NoPen)
            r = part["size"]
            p.drawRoundedRect(QRectF(part["x"] - r / 2, part["y"] - r / 2, r, r * 0.72),
                              1.5, 1.5)
        p.end()


class TaskCard(widgets.GlassCard):
    toggled = Signal(object)
    history_requested = Signal(object)
    delete_requested = Signal(object)

    def __init__(self, task: core.Task, parent=None):
        super().__init__(parent, radius=14, alpha=180)
        self.task = task
        self.setFixedHeight(68)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 9, 13, 9)
        lay.setSpacing(10)

        kind = "accent" if task.is_cycle else "neutral"
        chip = widgets.Chip(core.TASK_TYPE_LABELS.get(task.type, "一次"), kind)
        lay.addWidget(chip, 0, Qt.AlignmentFlag.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(1)
        title = widgets.ElidedLabel(task.text, self)
        title_font = theme.font(12, theme.QFont.Weight.DemiBold)
        if task.done:
            title_font.setStrikeOut(True)
        title.setFont(title_font)
        title.setStyleSheet(
            f"color: {theme.C_SUB if task.done else theme.C_TEXT}; background: transparent;"
        )
        col.addWidget(title)

        meta_text, meta_color = self._meta_text(task)
        meta = ClickableLabel(meta_text, self)
        meta.setFont(theme.font(12))
        meta.setStyleSheet(f"color: {meta_color}; background: transparent;")
        if task.deadline or task.is_cycle or task.history:
            meta.setToolTip("点击查看完成日历")
            meta.clicked.connect(lambda: self.history_requested.emit(self.task))
        else:
            meta.setCursor(Qt.CursorShape.ArrowCursor)
        col.addWidget(meta)
        lay.addLayout(col, 1)

        if task.is_cycle or task.history:
            hist = widgets.AppButton("", "calendar", "ghost", "icon")
            hist.setFixedSize(30, 30)
            hist.setToolTip("查看完成记录")
            hist.clicked.connect(lambda: self.history_requested.emit(self.task))
            lay.addWidget(hist)

        check = TaskCheck(task.done, self)
        check.toggled.connect(lambda checked: self.toggled.emit(self.task))
        lay.addWidget(check, 0, Qt.AlignmentFlag.AlignVCenter)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

    @staticmethod
    def _meta_text(task: core.Task) -> tuple[str, str]:
        if task.type == "once":
            if not task.deadline:
                return "没有截止日期", theme.C_SUB
            state = core.task_due_state(task)
            due = core.format_cn_date(Date.fromisoformat(task.deadline))
            if state == "overdue":
                return f"截止 {due} · 已逾期", theme.C_RED
            if state == "today":
                return f"截止 {due} · 今天到期", theme.C_AMBER
            return f"截止 {due}", theme.C_SUB
        count = len(task.history)
        return (f"已完成 {count} 次" if count else "还没有完成记录"), theme.C_SUB

    def _menu(self, pos):
        menu = QMenu(self)
        if self.task.is_cycle or self.task.history:
            act = menu.addAction("查看完成记录")
            act.triggered.connect(lambda: self.history_requested.emit(self.task))
        act = menu.addAction("标记为未完成" if self.task.done else "标记为完成")
        act.triggered.connect(lambda: self.toggled.emit(self.task))
        menu.addSeparator()
        act = menu.addAction("删除此待办")
        act.triggered.connect(lambda: self.delete_requested.emit(self.task))
        menu.exec(self.mapToGlobal(pos))


class TaskPage(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data: core.AppData | None = None
        self.filter = "all"
        self._cards: list[TaskCard] = []
        self._build()

    # ------------------------------------------------------------ 构建
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        self.header = common.PageHeader("待办 · 学习节奏", "待办", hint="输入一行按回车即添加；勾选方框标记完成，右键查看更多操作")
        add = widgets.AppButton("新增待办", "plus", "primary", "md")
        add.clicked.connect(self._focus_add)
        self.header.add_action(add)
        root.addWidget(self.header)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)
        self.stat_total = widgets.StatTile("全部", "0", "条")
        self.stat_done = widgets.StatTile("已完成", "0", "条", color=theme.C_GREEN)
        self.stat_left = widgets.StatTile("未完成", "0", "条", color=theme.C_AMBER)
        self.stat_pct = widgets.StatTile("完成度", "0", "%", color=theme.C_GREEN)
        for tile in (self.stat_total, self.stat_done, self.stat_left, self.stat_pct):
            stats_row.addWidget(tile, 1)
        root.addLayout(stats_row)

        self.overall = widgets.SplitProgressBar(height=7)
        self.overall.setToolTip("绿色为已完成，红色为未完成")
        root.addWidget(self.overall)

        add_card = widgets.GlassCard(radius=14, alpha=166)
        al = QVBoxLayout(add_card)
        al.setContentsMargins(14, 11, 14, 11)
        al.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.input = QLineEdit()
        self.input.setPlaceholderText("添加一条待办，按回车确认…")
        self.input.setMinimumHeight(38)
        self.input.returnPressed.connect(self._add_task)
        row.addWidget(self.input, 1)
        self.add_btn = widgets.AppButton("添加", "plus", "primary", "md")
        self.add_btn.setFixedHeight(38)
        self.add_btn.clicked.connect(self._add_task)
        row.addWidget(self.add_btn)
        al.addLayout(row)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        self.type_seg = widgets.Segmented(
            [("daily", "每日"), ("weekly", "每周"), ("once", "一次")], "once"
        )
        self.type_seg.changed.connect(self._on_type)
        row2.addWidget(self.type_seg)
        self.due_label = widgets.label("截止日期", 12)
        row2.addWidget(self.due_label)
        self.due = widgets.DateField()
        self.due.setDate(QDate.currentDate().addDays(1))
        self.due.setFixedWidth(142)
        row2.addWidget(self.due)
        row2.addStretch(1)
        self.type_hint = widgets.label("一次性待办到期后会提醒", 12, theme.C_SUB)
        row2.addWidget(self.type_hint)
        al.addLayout(row2)
        root.addWidget(add_card)

        bar = QHBoxLayout()
        bar.setSpacing(9)
        self.filters = widgets.Segmented(
            [("all", "全部"), ("pending", "进行中"), ("done", "已完成")], "all"
        )
        self.filters.changed.connect(self._on_filter)
        bar.addWidget(self.filters)
        bar.addStretch(1)
        self.count_label = widgets.label("", 12)
        bar.addWidget(self.count_label)
        root.addLayout(bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_host = QWidget()
        self.list_host.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 0, 4, 4)
        self.list_layout.setSpacing(10)
        self.scroll.setWidget(self.list_host)
        root.addWidget(self.scroll, 1)

        self._on_type("once")
        self.overlay = ConfettiOverlay(self)
        self.overlay.setGeometry(self.rect())

    # ------------------------------------------------------------ 数据
    def set_data(self, data: core.AppData):
        self.data = data
        self.refresh()

    def _update_stats(self, tasks, total, done, pending, animate: bool = True):
        self.stat_total.set_value(str(total))
        self.stat_done.set_value(str(done))
        self.stat_left.set_value(str(pending))
        percent = int(round(done / total * 100)) if total else 0
        self.stat_pct.set_value(str(percent))
        self.overall.set_ratio(done, total, animate=animate)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "overlay"):
            self.overlay.setGeometry(self.rect())

    def refresh(self):
        if not self.data:
            return
        tasks = core.sorted_tasks(self.data.tasks)
        total, done, pending = core.task_stats(tasks)
        self._update_stats(tasks, total, done, pending, animate=False)
        now = datetime.now()
        today_text = f"{now.month} 月 {now.day} 日"
        self.header.set_subtitle(
            f"今天是 {today_text} · 共 {total} 条待办，已完成 {done} 条。"
        )

        shown = []
        for task in tasks:
            if self.filter == "pending" and task.done:
                continue
            if self.filter == "done" and not task.done:
                continue
            shown.append(task)
        self.count_label.setText(f"当前显示 {len(shown)} 条")
        self._clear_list()
        if not shown:
            if self.data.tasks:
                empty = widgets.EmptyState("filter", "这个筛选下没有待办",
                                           "切换到「全部」看看其它内容。")
            else:
                empty_add = widgets.AppButton("添加第一条待办", "plus", "primary", "lg")
                empty_add.clicked.connect(self._focus_add)
                empty = widgets.EmptyState(
                    "list", "还没有待办",
                    "在上面写一条，比如「背 30 个六级单词」，然后按回车。",
                    action=empty_add,
                )
            self.list_layout.addWidget(empty)
            self.list_layout.addStretch(1)
            return
        for task in shown:
            card = TaskCard(task)
            card.toggled.connect(self._toggle)
            card.history_requested.connect(self._show_history)
            card.delete_requested.connect(self._delete)
            self._cards.append(card)
            self.list_layout.addWidget(card)
        self.list_layout.addStretch(1)

    def _clear_list(self):
        self._cards.clear()
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    # ------------------------------------------------------------ 操作
    def _on_type(self, key: str):
        once = key == "once"
        self.due.setVisible(once)
        self.due_label.setVisible(once)
        self.type_hint.setText(
            "一次性待办到期后会提醒" if once else "循环待办会按天 / 周自动重置完成状态"
        )

    def _on_filter(self, key: str):
        self.filter = key
        self.refresh()

    def _focus_add(self):
        self.input.setFocus()

    def _add_task(self):
        if not self.data:
            return
        text = self.input.text().strip()
        if not text:
            self.input.setFocus()
            return
        ttype = self.type_seg.current()
        deadline = None
        if ttype == "once":
            d = self.due.date()
            deadline = Date(d.year(), d.month(), d.day()).isoformat()
        task = core.Task(core.new_id("t"), text[:120], ttype, deadline=deadline)
        self.data.tasks.append(task)
        self.input.clear()
        self.changed.emit()
        self.refresh()
        self.input.setFocus()

    def _toggle(self, task: core.Task):
        completed_now = not task.done
        if task.done:
            task.done = False
            task.done_date = None
        else:
            task.done = True
            today = Date.today()
            task.done_date = today.isoformat()
            task.history[today.isoformat()] = datetime.now().isoformat(timespec="seconds")
        self.changed.emit()
        tasks = core.sorted_tasks(self.data.tasks) if self.data else []
        total, done, pending = core.task_stats(tasks)
        self._update_stats(tasks, total, done, pending)
        if completed_now:
            card = next((c for c in self._cards if c.task is task), None)
            if card is not None:
                center = card.mapTo(self, card.rect().center())
                self.overlay.burst(QPointF(center))
            QTimer.singleShot(320, self.refresh)
        else:
            self.refresh()

    def _delete(self, task: core.Task):
        if not self.data:
            return
        if not widgets.ask_confirm(
            self.window(), "删除待办", f"确定删除「{task.text[:24]}」吗？"
        ):
            return
        self.data.tasks = [t for t in self.data.tasks if t.id != task.id]
        self.changed.emit()
        self.refresh()

    def _show_history(self, task: core.Task):
        TaskHistoryDialog(self.window(), task).exec()
