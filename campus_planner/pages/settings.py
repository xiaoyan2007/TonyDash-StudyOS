"""设置页：学期、作息、外观、数据与关于。"""
from __future__ import annotations

from datetime import date as Date

from PySide6.QtCore import QDate, QTime, Qt, Signal
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout, QLineEdit, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

from .. import core, theme, widgets
from ..credits import CreditsCard
from . import common


class SettingsPage(QWidget):
    changed = Signal()
    glass_changed = Signal(int)
    export_json = Signal()
    import_json = Signal()
    export_ics = Signal()
    clear_all = Signal()
    open_dir = Signal()
    about_requested = Signal()
    guide_requested = Signal()
    theme_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self.data: core.AppData | None = None
        self._period_rows: list[QWidget] = []
        self._build()

    # -- 构建
    def _section(self, icon: str, title: str, desc: str) -> tuple[widgets.GlassCard, QVBoxLayout]:
        card = widgets.GlassCard(radius=16, alpha=180)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 15, 18, 17)
        lay.setSpacing(10)
        # 表头单独包一层「固定高度」的控件：网格会把同一行的卡片拉到一样高，
        # 若表头能自由伸展，多出来的高度会挤到标题与说明之间，两栏的表头就会
        # 一个紧凑、一个松散。固定高度后多余空间统一落到卡片底部。
        head_w = QWidget(card)
        head_w.setStyleSheet("background: transparent;")
        head_w.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        head = QHBoxLayout(head_w)
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(9)
        head.addWidget(widgets.IconBadge(icon, 30))
        box = QVBoxLayout()
        box.setSpacing(1)
        t = QLabel(title)
        t.setFont(theme.font(13.5, theme.QFont.Weight.DemiBold))
        t.setStyleSheet("background: transparent;")
        s = QLabel(desc)
        s.setFont(theme.font(11.5))
        s.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        box.addWidget(t)
        box.addWidget(s)
        head.addLayout(box, 1)
        lay.addWidget(head_w)
        return card, lay

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        self.header = common.PageHeader("偏好 · 数据 · 关于", "设置",
                                        "课表、考试与待办数据只保存在本机，修改后自动保存。")
        root.addWidget(self.header)

        scroll = QScrollArea()
        self.scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        host = QWidget()
        host.setStyleSheet("background: transparent;")
        self.grid = QGridLayout(host)
        self.grid.setContentsMargins(0, 2, 6, 8)
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(12)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)
        self.grid.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        scroll.setWidget(host)
        root.addWidget(scroll, 1)

        # 学期
        term_card, term = self._section("calendar", "学期", "决定周次与日期换算")
        self.term_name = QLineEdit()
        self.term_name.setMinimumHeight(36)
        self.term_name.setPlaceholderText("如：2026–2027 秋季学期")
        self.term_name.editingFinished.connect(self._on_term_name)
        term.addWidget(common.field_row("学期名称", self.term_name))
        dates = QHBoxLayout()
        dates.setSpacing(10)
        self.term_start = widgets.DateField()
        self.term_start.dateChanged.connect(self._on_term_start)
        self.term_start.setMaximumWidth(220)
        dates.addWidget(common.field_row("开学第一周周一", self.term_start), 1)
        self.total_weeks = QLineEdit()
        self.total_weeks.setValidator(QIntValidator(1, 30))
        self.total_weeks.setFixedWidth(74)
        self.total_weeks.setMinimumHeight(36)
        self.total_weeks.editingFinished.connect(self._on_total_weeks)
        dates.addWidget(common.field_row("总周数", self.total_weeks), 1)
        term.addLayout(dates)
        weekend = QHBoxLayout()
        weekend.addWidget(widgets.label("课表显示周末", 11))
        weekend.addStretch(1)
        self.weekend_switch = widgets.Switch()
        self.weekend_switch.toggled.connect(self._on_weekend)
        weekend.addWidget(self.weekend_switch)
        term.addLayout(weekend)
        term.addStretch(1)
        term_card.setMinimumHeight(206)
        self.grid.addWidget(term_card, 0, 0)

        # 外观
        look_card, look = self._section("spark", "外观", "深浅主题、毛玻璃强度与动效")
        theme_row = QHBoxLayout()
        theme_row.setSpacing(10)
        theme_row.addWidget(widgets.label("界面主题", 12))
        theme_row.addStretch(1)
        self.theme_seg = widgets.Segmented([("light", "浅色"), ("dark", "深色")], "light")
        self.theme_seg.setFixedWidth(150)
        self.theme_seg.changed.connect(self._on_theme)
        theme_row.addWidget(self.theme_seg)
        look.addLayout(theme_row)
        look.addWidget(widgets.hline())
        row = QHBoxLayout()
        row.addWidget(widgets.label("毛玻璃强度", 12))
        row.addStretch(1)
        self.glass_value = widgets.label("70%", 11.5, theme.C_BLUE)
        row.addWidget(self.glass_value)
        look.addLayout(row)
        self.glass_slider = widgets.SmoothSlider()
        self.glass_slider.setRange(20, 100)
        self.glass_slider.setValue(70)
        self.glass_slider.valueChanged.connect(self._on_glass)
        self.glass_slider.sliderReleased.connect(self._on_glass_done)
        look.addWidget(self.glass_slider)
        note = widgets.label("数值越高，背景越模糊、卡片越通透；拖动时背景会连续变化。",
                             11, theme.C_SUB)
        note.setWordWrap(True)
        look.addWidget(note)
        motion = QHBoxLayout()
        motion.addWidget(widgets.label("减少动画", 12))
        motion.addStretch(1)
        self.motion_switch = widgets.Switch()
        self.motion_switch.toggled.connect(self._on_motion)
        motion.addWidget(self.motion_switch)
        look.addLayout(motion)
        look.addStretch(1)
        look_card.setMinimumHeight(292)
        self.grid.addWidget(look_card, 0, 1)

        # 作息
        period_card, period = self._section("clock", "作息时间", "默认采用浙江工商大学作息，可随时增删")
        tools = QHBoxLayout()
        tools.setSpacing(7)
        for text, icon, handler in (
            ("添加一节", "plus", self._add_period),
            ("删除末节", "trash", self._remove_period),
            ("按 45 分钟重排", "refresh", self._redistribute),
            ("采用浙江工商大学作息", "refresh", self._reset_periods),
        ):
            b = widgets.AppButton(text, icon, "ghost", "sm")
            b.clicked.connect(handler)
            tools.addWidget(b)
        tools.addStretch(1)
        period.addLayout(tools)
        self.period_box = QVBoxLayout()
        self.period_box.setSpacing(6)
        period.addLayout(self.period_box)
        period.addStretch(1)
        self.grid.addWidget(period_card, 1, 0, 1, 2)

        # 数据
        data_card, data_lay = self._section("download", "数据", "导入导出、备份与迁移")
        btns = QGridLayout()
        btns.setHorizontalSpacing(8)
        btns.setVerticalSpacing(8)
        for i, (text, icon, kind, signal) in enumerate((
            ("导出备份 JSON", "download", "white", self.export_json),
            ("从 JSON 导入", "upload", "white", self.import_json),
            ("导出日历 .ics", "calendar", "white", self.export_ics),
            ("打开数据文件夹", "folder", "white", self.open_dir),
            ("清空全部数据", "trash", "danger", self.clear_all),
        )):
            b = widgets.AppButton(text, icon, kind, "sm")
            b.clicked.connect(self._emit_signal(signal))
            btns.addWidget(b, i // 2, i % 2)
        data_lay.addLayout(btns)
        self.path_label = widgets.label("", 11.5, theme.C_SUB)
        self.path_label.setWordWrap(True)
        data_lay.addWidget(self.path_label)
        data_lay.addWidget(widgets.label("所有修改都会自动保存；换电脑时用 JSON 备份迁移即可。",
                                         11.5, theme.C_SUB))
        data_lay.addStretch(1)
        self.grid.addWidget(data_card, 2, 0)

        # 关于
        about_card, about = self._section("info", "关于", "TonyDash学习终端 · 课表 / 考试 / 待办")
        for text in (
            "为本科同学准备的学习节奏工具：课表、期末考试与待办，全都收进一块玻璃里。",
            "快捷键：Ctrl+1–4 切页，Ctrl+N 新建，← → 换周，Ctrl+, 设置。",
            f"数据格式 v{core.DATA_VERSION}，纯本地存储，不联网。",
        ):
            line = widgets.label(text, 12, theme.C_SUB)
            line.setWordWrap(True)
            about.addWidget(line)
        about.addStretch(1)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        about_btn = widgets.AppButton("关于与更新日志", "info", "white", "sm")
        about_btn.clicked.connect(self.about_requested.emit)
        btn_row.addWidget(about_btn)
        guide_btn = widgets.AppButton("重新查看上手引导", "spark", "soft", "sm")
        guide_btn.clicked.connect(self.guide_requested.emit)
        btn_row.addWidget(guide_btn)
        btn_row.addStretch(1)
        about.addLayout(btn_row)
        version = widgets.label(f"版本 {core.APP_VERSION} · {core.APP_NAME}", 11.5, theme.C_SUB)
        about.addWidget(version)
        self.grid.addWidget(about_card, 2, 1)

        # 鸣谢名单（设置页最下方）
        self.credits_card = CreditsCard(self)
        self.grid.addWidget(self.credits_card, 3, 0, 1, 2)
        self.grid.setRowStretch(4, 1)

    def _emit_signal(self, signal):
        def run():
            signal.emit()
        return run

    # -- 数据
    def set_data(self, data: core.AppData):
        self.data = data
        s = data.settings
        self.term_name.setText(s.term_name)
        self.term_start.blockSignals(True)
        self.term_start.setDate(QDate(s.term_start.year, s.term_start.month, s.term_start.day))
        self.term_start.blockSignals(False)
        self.total_weeks.setText(str(s.total_weeks))
        self.weekend_switch.blockSignals(True)
        self.weekend_switch.setChecked(s.show_weekend)
        self.weekend_switch.blockSignals(False)
        self.glass_slider.blockSignals(True)
        self.glass_slider.setValue(int(s.glass))
        self.glass_slider.blockSignals(False)
        self.glass_value.setText(f"{int(s.glass)}%")
        self.motion_switch.blockSignals(True)
        self.motion_switch.setChecked(s.reduce_motion)
        self.motion_switch.blockSignals(False)
        self.path_label.setText(f"数据文件：{core.data_path()}")
        self._rebuild_periods()

    # -- 学期
    def _on_term_name(self):
        if not self.data:
            return
        name = self.term_name.text().strip() or core.default_term_name()
        self.data.settings.term_name = name
        self.changed.emit()

    def _on_term_start(self, qdate):
        if not self.data:
            return
        d = Date(qdate.year(), qdate.month(), qdate.day())
        monday = core.monday_of(d)
        self.data.settings.term_start = monday
        if monday != d:
            self.term_start.blockSignals(True)
            self.term_start.setDate(QDate(monday.year, monday.month, monday.day))
            self.term_start.blockSignals(False)
        self.changed.emit()

    def _on_total_weeks(self):
        if not self.data:
            return
        try:
            total = int(self.total_weeks.text().strip() or "18")
        except ValueError:
            total = 18
        total = core.clamp(total, 1, 30)
        self.total_weeks.setText(str(total))
        self.data.settings.total_weeks = total
        self.changed.emit()

    def _on_weekend(self, checked: bool):
        if not self.data:
            return
        self.data.settings.show_weekend = bool(checked)
        self.changed.emit()

    # -- 外观
    def sync_theme(self):
        mode = getattr(self.data, "settings", None)
        mode = getattr(mode, "theme_mode", "light") if mode else "light"
        self.theme_seg.blockSignals(True)
        self.theme_seg.set_current(mode, emit=False)
        self.theme_seg.blockSignals(False)
        for picker in self.findChildren(widgets.TimePicker):
            picker.apply_theme()
        # 设置页是「不重建、只 sync_theme」的页面，写死过颜色的标签要在这里重刷
        widgets.refresh_themed(self)
        if hasattr(self, "header"):
            self.header.sync_theme()

    def _on_theme(self, mode: str):
        if not self.data:
            return
        self.data.settings.theme_mode = "dark" if mode == "dark" else "light"
        self.theme_requested.emit(self.data.settings.theme_mode)

    def _on_glass(self, value: int):
        if hasattr(self, "glass_value"):
            self.glass_value.setText(f"{value}%")
        if self.data:
            self.data.settings.glass = value
        self.glass_changed.emit(int(value))

    def _on_glass_done(self):
        if self.data:
            self.changed.emit()

    def _on_motion(self, checked: bool):
        if not self.data:
            return
        self.data.settings.reduce_motion = bool(checked)
        self.changed.emit()

    # -- 作息
    def _rebuild_periods(self):
        while self.period_box.count():
            item = self.period_box.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self._period_rows.clear()
        if not self.data:
            return
        for i, period in enumerate(self.data.periods):
            row = QWidget()
            row.setStyleSheet("background: transparent;")
            row.setMinimumHeight(40)
            lay = QHBoxLayout(row)
            lay.setContentsMargins(0, 1, 0, 1)
            lay.setSpacing(10)
            idx = QLabel(f"第 {i + 1} 节")
            idx.setFixedWidth(64)
            idx.setFont(theme.font(11.5, theme.QFont.Weight.DemiBold))
            idx.setStyleSheet(f"color: {theme.C_TEXT}; background: transparent;")
            start = widgets.TimePicker()
            start.set_time(period.start)
            start.setFixedWidth(150)
            start.changed.connect(lambda value, i=i: self._set_period_text(i, "start", value))
            end = widgets.TimePicker()
            end.set_time(period.end)
            end.setFixedWidth(150)
            end.changed.connect(lambda value, i=i: self._set_period_text(i, "end", value))
            dur = QLabel("")
            dur.setFont(theme.font(11, theme.QFont.Weight.DemiBold))
            dur.setFixedWidth(70)
            dur.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            dur.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
            lay.addWidget(idx)
            lay.addWidget(start)
            dash = QLabel("—")
            dash.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
            lay.addWidget(dash)
            lay.addWidget(end)
            lay.addWidget(dur)
            lay.addStretch(1)
            self.period_box.addWidget(row)
            self._period_rows.append(row)
            self._update_duration(i, dur)
            if i < len(self.data.periods) - 1:
                line = QFrame()
                line.setFixedHeight(1)
                line.setStyleSheet(theme.divider_style(18))
                self.period_box.addWidget(line)
        hint = widgets.label("修改时间后，课表里的上课时间会立即更新。", 12, theme.C_SUB)
        self.period_box.addWidget(hint)

    def _update_duration(self, index: int, label: QLabel | None = None):
        if not self.data or index >= len(self.data.periods):
            return
        p = self.data.periods[index]
        minutes = core.time_to_minutes(p.end) - core.time_to_minutes(p.start)
        if label is None and index < len(self._period_rows):
            labels = self._period_rows[index].findChildren(QLabel)
            label = labels[-1] if labels else None
        if label is not None:
            if minutes <= 0:
                label.setText("时间有误")
                label.setStyleSheet(f"color: {theme.C_RED}; background: transparent;")
            else:
                label.setText(f"{minutes} 分钟")
                label.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")

    def _set_period_text(self, index: int, field: str, value: str):
        if not self.data or index >= len(self.data.periods):
            return
        normalized = core.norm_hhmm(value, getattr(self.data.periods[index], field))
        setattr(self.data.periods[index], field, normalized)
        row = self._period_rows[index] if index < len(self._period_rows) else None
        if row:
            labels = row.findChildren(QLabel)
            if labels:
                self._update_duration(index, labels[-1])
        self.changed.emit()

    def _set_period(self, index: int, field: str, qtime: QTime):
        if not self.data or index >= len(self.data.periods):
            return
        text = f"{qtime.hour():02d}:{qtime.minute():02d}"
        setattr(self.data.periods[index], field, text)
        row = self._period_rows[index] if index < len(self._period_rows) else None
        if row:
            labels = row.findChildren(QLabel)
            if labels:
                self._update_duration(index, labels[-1])
        self.changed.emit()

    def _clamp_courses(self):
        if not self.data:
            return
        total = len(self.data.periods)
        for c in self.data.courses:
            c.start = core.clamp(c.start, 1, total)
            c.end = core.clamp(c.end, c.start, total)

    def _add_period(self):
        if not self.data:
            return
        if len(self.data.periods) >= 16:
            widgets.Toast("最多 16 节课", "warn", self.window()).show_at(self.window().rect())
            return
        last = self.data.periods[-1]
        start_min = core.time_to_minutes(last.start) + 65
        if start_min > 23 * 60:
            start_min = 23 * 60
        self.data.periods.append(core.Period(core.minutes_to_time(start_min),
                                             core.minutes_to_time(min(start_min + 45, 23 * 60 + 59))))
        self._rebuild_periods()
        self.changed.emit()

    def _remove_period(self):
        if not self.data:
            return
        if len(self.data.periods) <= 2:
            widgets.Toast("至少保留 2 节课", "warn", self.window()).show_at(self.window().rect())
            return
        self.data.periods.pop()
        self._clamp_courses()
        self._rebuild_periods()
        self.changed.emit()

    def _redistribute(self):
        if not self.data:
            return
        self.data.periods = core.redistribute_periods(self.data.periods, 45, 10)
        self._rebuild_periods()
        self.changed.emit()

    def _reset_periods(self):
        if not self.data:
            return
        self.data.periods = core.default_periods()
        self._clamp_courses()
        self._rebuild_periods()
        self.changed.emit()
