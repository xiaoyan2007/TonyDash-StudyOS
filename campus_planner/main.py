"""主窗口：无边框圆角窗口、侧栏导航、四个页面与数据流。"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QRectF, QSize, Qt, QTimer, QPropertyAnimation, QAbstractAnimation
from PySide6.QtGui import (
    QColor, QCursor, QDesktopServices, QPainter, QPainterPath, QPen, QPixmap, QShortcut,
    QKeySequence,
)
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QApplication, QAbstractButton, QAbstractSpinBox, QButtonGroup, QComboBox, QDateEdit,
    QFileDialog, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QStackedWidget, QTimeEdit, QVBoxLayout, QWidget,
)

from . import core, dialogs, onboarding, schedule_import, theme, widgets
from .about_dialogs import AboutDialog
from .pages import common, exams, home, schedule, settings, todo, wordbook


class TitleBar(QWidget):
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._window = window
        self.setFixedHeight(46)
        self.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 4, 0)
        lay.setSpacing(8)

        mark = widgets.IconBadge("cap", 30)
        lay.addWidget(mark)
        brand = QVBoxLayout()
        brand.setContentsMargins(0, 0, 0, 0)
        brand.setSpacing(0)
        self.brand_name = QLabel(core.APP_NAME)
        self.brand_name.setFont(theme.font(15, theme.QFont.Weight.DemiBold))
        self.brand_name.setStyleSheet(f"color: {theme.C_TEXT}; background: transparent;")
        brand.addWidget(self.brand_name)
        self.sub = QLabel(core.APP_SUBTITLE)
        self.sub.setFont(theme.font(11.5))
        self.sub.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        brand.addWidget(self.sub)
        lay.addLayout(brand)
        lay.addStretch(1)

        self.theme_btn = widgets.AppButton("", "moon", "ghost", "icon")
        self.theme_btn.setFixedSize(44, 34)
        self.theme_btn.setToolTip("切换深色 / 浅色模式")
        self.theme_btn.clicked.connect(self._window.toggle_theme)
        lay.addWidget(self.theme_btn)

        self._win_buttons = []
        for icon, tip, handler, danger in (
            ("min", "最小化", self._window.showMinimized, False),
            ("max", "最大化", self._window.toggle_max, False),
            ("close", "关闭", self._window.close, True),
        ):
            b = QPushButton(theme.icon_char(icon))
            b.setFont(theme.icon_font(9.5))
            b.setFixedSize(34, 26)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(tip)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setStyleSheet(self._win_button_qss(danger))
            b.clicked.connect(handler)
            lay.addWidget(b)
            self._win_buttons.append((b, danger))

    @staticmethod
    def _win_button_qss(danger: bool) -> str:
        if danger:
            return (
                "QPushButton{background:transparent;border:none;border-radius:7px;color:" + theme.C_SUB + ";}"
                "QPushButton:hover{background:#FF3B30;color:white;}"
                "QPushButton:pressed{background:#D92D22;color:white;}"
            )
        return (
            "QPushButton{background:transparent;border:none;border-radius:7px;color:" + theme.C_SUB + ";}"
            "QPushButton:hover{background:rgba(10,40,90,16);color:" + theme.C_TEXT + ";}"
            "QPushButton:pressed{background:rgba(10,40,90,28);}"
        )

    def apply_theme(self):
        """切换主题后重新写入标题栏里被烘焙的颜色。"""
        self.brand_name.setStyleSheet(f"color: {theme.C_TEXT}; background: transparent;")
        self.sub.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        for b, danger in self._win_buttons:
            b.setStyleSheet(self._win_button_qss(danger))
        self.theme_btn.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            wh = self._window.windowHandle()
            if wh is not None:
                wh.startSystemMove()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._window.toggle_max()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(core.APP_NAME)
        self.setWindowIcon(theme.app_icon())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setMinimumSize(1080, 680)
        self.resize(1280, 820)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)

        self.data = core.load_data()
        # 旧版本的示例数据不再保留：升级后第一次启动回到空白状态
        if getattr(self.data, "sample", False):
            self.data = core.blank_data()
            core.save_data(self.data)
        self.week = core.current_week(self.data.settings.term_start,
                                      self.data.settings.total_weeks)
        self._backdrop: QPixmap | None = None
        self._glass_ver = -1
        self._radius = 18
        self._toast = widgets.ToastHost(self)
        # 页面懒加载状态
        self._page_objs: list = [None, None, None, None, None, None]
        self._page_built = [False, False, False, False, False, False]
        self._theme_anim: QPropertyAnimation | None = None

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self._save_now)

        self._backdrop_timer = QTimer(self)
        self._backdrop_timer.setSingleShot(True)
        self._backdrop_timer.setInterval(16)
        self._backdrop_timer.timeout.connect(self._rebuild_backdrop)

        self._build()
        self._apply_theme(rebuild=False)
        self._bind_shortcuts()
        self.go(0)
        self._sync_chrome()
        if core.rollover_tasks(self.data.tasks):
            try:
                core.save_data(self.data)
            except OSError:
                pass
        self._day_timer = QTimer(self)
        self._day_timer.setInterval(60_000)
        self._day_timer.timeout.connect(self._check_day_rollover)
        self._day_timer.start()
        self._coach: onboarding.CoachOverlay | None = None

    # ------------------------------------------------------------ 构建
    def _build(self):
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(22, 14, 22, 18)
        self.outer.setSpacing(10)

        self.titlebar = TitleBar(self)
        self.outer.addWidget(self.titlebar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(14)
        self.outer.addLayout(body, 1)

        # 侧栏
        self.rail = widgets.GlassCard(radius=16, alpha=190)
        self.rail.setFixedWidth(196)
        rail = QVBoxLayout(self.rail)
        rail.setContentsMargins(10, 12, 10, 12)
        rail.setSpacing(4)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: list[widgets.NavButton] = []
        self.nav_targets = [0, 1, 2, 3, 4, 5]  # 主页 / 课表 / 待办 / 考试 / 设置 / 单词本
        for i, (icon, label) in enumerate((("home", "主页"),
                                           ("calendar", "课程表"),
                                           ("list", "待办"),
                                           ("report", "期末考试"),
                                           ("gear", "设置"),
                                           ("books", "单词本"))):
            target = self.nav_targets[i]
            b = widgets.NavButton(icon, label)
            b.setCheckable(True)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _=False, idx=target: self.go(idx))
            self.nav_group.addButton(b, i)
            self.nav_buttons.append(b)
            rail.addWidget(b)
        rail.addSpacing(10)
        rail.addWidget(widgets.hline())
        rail.addSpacing(10)

        self.term_card = widgets.GlassCard(radius=12, alpha=158)
        tc = QVBoxLayout(self.term_card)
        tc.setContentsMargins(12, 11, 12, 12)
        tc.setSpacing(6)
        self.rail_cap = widgets.label("本学期", 11.5, theme.C_SUB, theme.QFont.Weight.DemiBold)
        tc.addWidget(self.rail_cap)
        self.term_name = QLabel()
        self.term_name.setFont(theme.font(11.5, theme.QFont.Weight.DemiBold))
        self.term_name.setWordWrap(True)
        self.term_name.setStyleSheet(f"color: {theme.C_TEXT}; background: transparent;")
        tc.addWidget(self.term_name)
        self.week_line = widgets.label("", 12, theme.C_SUB)
        tc.addWidget(self.week_line)
        self.week_bar = widgets.ProgressBar(value=0, color=theme.C_BLUE, height=5)
        tc.addWidget(self.week_bar)
        self.term_extra = widgets.label("", 11.5, theme.C_SUB)
        tc.addWidget(self.term_extra)
        rail.addWidget(self.term_card)
        rail.addStretch(1)

        self.status_label = QLabel()
        self.status_label.setFont(theme.font(12))
        self.status_label.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        self.status_label.setWordWrap(True)
        rail.addWidget(self.status_label)
        body.addWidget(self.rail)

        # 主区域
        self.main_card = widgets.GlassCard(radius=20, alpha=182)
        main = QVBoxLayout(self.main_card)
        main.setContentsMargins(24, 20, 24, 22)
        main.setSpacing(0)
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background: transparent;")
        for _ in range(6):
            placeholder = QWidget()
            placeholder.setStyleSheet("background: transparent;")
            self.stack.addWidget(placeholder)
        main.addWidget(self.stack)
        body.addWidget(self.main_card, 1)

    # 页面按需构建：启动时只占位，避免一次性构造 5 个页面拖慢显示。
    def _ensure_page(self, index: int):
        if self._page_built[index]:
            return self._page_objs[index]
        if index == 0:
            page = home.HomePage()
        elif index == 1:
            page = schedule.SchedulePage()
        elif index == 2:
            page = todo.TaskPage()
        elif index == 3:
            page = exams.ExamPage()
        elif index == 4:
            page = settings.SettingsPage()
        else:
            page = wordbook.WordbookPageHost()
        page.setStyleSheet("background: transparent;")
        placeholder = self.stack.widget(index)
        self.stack.removeWidget(placeholder)
        placeholder.deleteLater()
        self.stack.insertWidget(index, page)
        self._page_objs[index] = page
        self._page_built[index] = True
        self._bind_page_signals(index, page)
        return page

    def _bind_page_signals(self, index: int, page) -> None:
        if index == 0:
            page.navigate.connect(self.go)
        elif index == 1:
            page.week_changed.connect(self._on_week)
            page.new_course.connect(self.new_course)
            page.edit_course.connect(self.edit_course)
            page.sample_action.connect(self._on_sample_action)
            page.import_requested.connect(self.open_import_dialog)
        elif index == 2:
            page.changed.connect(self._on_todo_changed)
        elif index == 3:
            page.new_exam.connect(self.new_exam)
            page.edit_exam.connect(self.edit_exam)
            page.duplicate_exam.connect(self.duplicate_exam)
            page.delete_exam.connect(self.delete_exam)
            page.export_ics.connect(self.export_ics)
            page.refresh_requested.connect(self._sync_chrome)
        elif index == 5:
            page.changed.connect(self._on_wordbook_changed)
        else:
            page.changed.connect(self._on_settings_changed)
            page.glass_changed.connect(self._on_glass)
            page.export_json.connect(self.export_json)
            page.import_json.connect(self.import_json)
            page.export_ics.connect(self.export_ics)
            page.clear_all.connect(self.clear_all)
            page.open_dir.connect(self.open_data_dir)
            page.about_requested.connect(self.show_about)
            page.guide_requested.connect(lambda: self.start_onboarding(force=True))
            page.theme_requested.connect(self.set_theme_mode)

    def _apply_page_data(self, index: int, page) -> None:
        if index == 1:
            page.set_data(self.data, self.week)
        else:
            page.set_data(self.data)

    @property
    def home_page(self):
        return self._ensure_page(0)

    @property
    def schedule_page(self):
        return self._ensure_page(1)

    @property
    def todo_page(self):
        return self._ensure_page(2)

    @property
    def exams_page(self):
        return self._ensure_page(3)

    @property
    def settings_page(self):
        return self._ensure_page(4)

    # ------------------------------------------------------------ 上手引导
    def start_onboarding(self, force: bool = False):
        if self._coach is not None and self._coach.isVisible():
            return
        if self.data.settings.onboarded and not force:
            return
        steps = onboarding.build_default_steps(
            self.home_page.start_button,
            self.todo_page.input,
            self.exams_page.header.actions.itemAt(1).widget(),
        )
        self._coach = onboarding.CoachOverlay(self, steps, self)
        self._coach.set_page_handler(self._onboard_go)
        self._coach.finished.connect(self._on_onboard_done)
        self._coach.start()

    def _onboard_go(self, page: int):
        self.go(page)
        self.raise_()
        if self._coach is not None:
            self._coach.raise_()

    def _on_onboard_done(self, completed: bool):
        self.data.settings.onboarded = True
        self._save_now()
        self._toast.show_message(
            "引导已完成，随时可以在设置里重新查看"
            if completed else "已跳过引导，设置里可以重新打开",
            "info", "重新引导", lambda: self.start_onboarding(force=True),
        )
        self._coach = None

    def _bind_shortcuts(self):
        bindings = (
            ("Ctrl+1", lambda: self.go(0)),
            ("Ctrl+2", lambda: self.go(1)),
            ("Ctrl+3", lambda: self.go(2)),
            ("Ctrl+4", lambda: self.go(3)),
            ("Ctrl+5", lambda: self.go(4)),
            ("Ctrl+N", self._new_current),
            ("Ctrl+,", lambda: self.go(4)),
            ("Left", lambda: self._key_week(-1)),
            ("Right", lambda: self._key_week(1)),
        )
        self._shortcuts = []
        for seq, handler in bindings:
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ShortcutContext.WindowShortcut)
            sc.activated.connect(handler)
            self._shortcuts.append(sc)

    # ------------------------------------------------------------ 背景
    def _rebuild_backdrop(self):
        dpr = self.devicePixelRatioF() or 1.0
        size = QSize(max(1, int(self.width() * dpr)), max(1, int(self.height() * dpr)))
        pm = theme.build_backdrop(size, int(self.data.settings.glass))
        pm.setDevicePixelRatio(dpr)
        self._backdrop = pm
        self._glass_ver = int(self.data.settings.glass)
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._backdrop_timer.start()
        if self._coach is not None and self._coach.isVisible():
            self._coach.setGeometry(self.rect())
        if self._toast._toast is not None:
            self._toast._toast.hide_animated()

    def showEvent(self, event):
        super().showEvent(event)
        if self._backdrop is None:
            self._rebuild_backdrop()
        if not self.data.settings.onboarded and self._coach is None:
            QTimer.singleShot(320, self.start_onboarding)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._apply_window_radius()
            self._backdrop_timer.start()
            maxed = bool(self.windowState() & Qt.WindowState.WindowMaximized)
            self.titlebar.sub.setVisible(not maxed)

    def _apply_window_radius(self):
        maxed = bool(self.windowState() & Qt.WindowState.WindowMaximized)
        r = 0 if maxed else 18
        if r == self._radius:
            return
        self._radius = r
        m = 0 if maxed else 22
        self.outer.setContentsMargins(m, 0 if maxed else 14, m, 0 if maxed else 18)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)
        if self._backdrop is not None:
            p.setClipPath(path)
            p.drawPixmap(0, 0, self._backdrop)
            p.setClipping(False)
        else:
            p.fillPath(path, QColor(theme.tokens()["backdrop"][1]))
        p.setPen(QPen(QColor(255, 255, 255, 210), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.end()

    # ------------------------------------------------------------ 导航
    def go(self, index: int):
        index = core.clamp(index, 0, 5)
        page = self._ensure_page(index)
        self.stack.setCurrentIndex(index)
        for i, b in enumerate(self.nav_buttons):
            b.setChecked(self.nav_targets[i] == index)
        self._apply_page_data(index, page)
        self._sync_chrome()

    def _sync_chrome(self):
        d = self.data
        self.week = core.clamp(self.week, 1, d.settings.total_weeks)
        _total_tasks, _done_tasks, pending_tasks = core.task_stats(d.tasks)
        self.nav_buttons[0].set_count(0)
        self.nav_buttons[1].set_count(len(d.courses))
        self.nav_buttons[2].set_count(pending_tasks)
        self.nav_buttons[3].set_count(len(core.upcoming_exams(d.exams)))
        self.term_name.setText(d.settings.term_name or core.default_term_name())
        self.week_line.setText(f"第 {self.week} 周 / 共 {d.settings.total_weeks} 周")
        self.week_bar.setValue(int(self.week / max(1, d.settings.total_weeks) * 100))
        self.term_extra.setText(f"{len(d.courses)} 门课程 · {len(d.exams)} 场考试 · {len(d.tasks)} 条待办")
        self._render_status()

    def _render_status(self):
        pending = self._save_timer.isActive()
        if pending:
            self.status_label.setText("● 正在保存…")
            return
        self.status_label.setText(f"● 数据已保存在本机\n{core.data_path().parent.name} / data.json")

    # ------------------------------------------------------------ 主题
    def _apply_theme(self, rebuild: bool = True):
        mode = self.data.settings.theme_mode
        theme.set_theme(mode)
        theme.apply_global_qss()
        self._glass_ver = -1
        self.titlebar.apply_theme()
        self.titlebar.theme_btn.icon_name = "sun" if theme.MODE == "dark" else "moon"
        self.titlebar.theme_btn.setToolTip(
            "切换到浅色模式" if theme.MODE == "dark" else "切换到深色模式")
        self.titlebar.theme_btn.update()
        if rebuild:
            self._apply_chrome_theme()
            self._rebuild_theme_pages()
            self.update()
        self._backdrop_timer.start(0)

    def _apply_chrome_theme(self):
        """侧栏与底部的静态文字颜色在构造时就写死了，切主题要重新写一遍。"""
        for lab in (self.rail_cap, self.week_line, self.term_extra):
            lab.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        self.term_name.setStyleSheet(f"color: {theme.C_TEXT}; background: transparent;")
        self.status_label.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        self.week_bar.set_color(theme.C_BLUE)
        for b in self.nav_buttons:
            b.update()
        # 侧栏的 hline / divider 不会被页面重建覆盖，这里按新主题重刷一遍。
        for frame in self.findChildren(QFrame):
            if frame.objectName() == "hline":
                frame.setStyleSheet(theme.divider_style(14))
            elif frame.objectName() == "divider":
                frame.setStyleSheet(theme.divider_style(16))

    def _rebuild_theme_pages(self):
        """页面构造时把主题色写进了各自的样式表，切主题只能重建。
        只重建当前可见页，其余页面丢回占位、按需重建，避免切换时明显卡顿。"""
        cur = self.stack.currentIndex()
        built = [i for i, flag in enumerate(self._page_built) if flag]
        if not built:
            return
        old = {}
        for index in built:
            old[index] = self.stack.widget(index)
        self._page_objs = [None, None, None, None, None, None]
        self._page_built = [False, False, False, False, False, False]
        for index in built:
            w = old.get(index)
            if w is not None:
                w.hide()
                self.stack.removeWidget(w)
                w.setParent(None)
                w.deleteLater()
            placeholder = QWidget()
            placeholder.setStyleSheet("background: transparent;")
            self.stack.insertWidget(index, placeholder)
        if cur in built:
            page = self._ensure_page(cur)
            self._apply_page_data(cur, page)
            if hasattr(page, "sync_theme"):
                page.sync_theme()
        self.stack.setCurrentIndex(cur)

    def set_theme_mode(self, mode: str):
        self._switch_theme("dark" if mode == "dark" else "light")

    def toggle_theme(self):
        if self._theme_anim is not None and self._theme_anim.state() == QAbstractAnimation.State.Running:
            return
        self._switch_theme("light" if theme.MODE == "dark" else "dark")
        self.toast("已切换到深色模式" if theme.MODE == "dark" else "已切换到浅色模式", "info")

    def _switch_theme(self, new_mode: str):
        """日 / 夜切换：截取当前画面，换主题后用半透明叠层淡出，
        背景与文字一起平滑过渡，而不是瞬间跳变。"""
        if theme.MODE == new_mode:
            return
        shot = None
        try:
            if self.isVisible():
                shot = self.grab()
        except Exception:
            shot = None
        self.data.settings.theme_mode = new_mode
        self._apply_theme(rebuild=True)
        # 仅当设置页已构建时才同步分段控件，避免切换主题时顺带构造整页
        if self._page_built[4]:
            self.settings_page.sync_theme()
        self._save_timer.start()
        if shot is None or shot.isNull():
            return
        overlay = QLabel(self)
        overlay.setPixmap(shot)
        overlay.setGeometry(0, 0, max(1, self.width()), max(1, self.height()))
        overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        effect = QGraphicsOpacityEffect(overlay)
        overlay.setGraphicsEffect(effect)
        overlay.show()
        overlay.raise_()
        anim = QPropertyAnimation(effect, b"opacity", self, duration=420)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(overlay.deleteLater)
        self._theme_anim = anim
        anim.start()

    # ------------------------------------------------------------ 保存
    def commit(self, refresh: bool = True):
        self._save_timer.start()
        self._sync_chrome()
        if refresh:
            self._refresh_pages()

    def _save_now(self):
        try:
            core.save_data(self.data)
        except OSError as exc:
            self.toast(f"保存失败：{exc}", "err")
        self._render_status()

    def _refresh_pages(self):
        self.week = core.clamp(self.week, 1, self.data.settings.total_weeks)
        for index, page in enumerate(self._page_objs):
            # 设置页不在此处刷新：它的 changed 信号会重新进入这里，
            # 否则每次编辑作息都会重建整页、抢走正在输入的焦点。
            if page is not None and index != 4:
                self._apply_page_data(index, page)

    def _on_settings_changed(self):
        self._on_glass(self.data.settings.glass, apply_only=True)
        # 开学日期或总周数一改，当前周次必须重新按今天算一遍；
        # 只做 clamp 的话左栏的学期进度条不会跟着动。
        self.week = core.current_week(self.data.settings.term_start,
                                      self.data.settings.total_weeks)
        self.commit(refresh=True)

    def _on_glass(self, value: int, apply_only: bool = False):
        self.data.settings.glass = int(value)
        if self._glass_ver != int(value):
            # 拖动时用 16ms 合并重绘，连续拖动近似实时
            self._backdrop_timer.start(16)
        self._save_timer.start()
        self._render_status()

    def _on_todo_changed(self):
        self._save_timer.start()
        self._sync_chrome()
        self._render_status()

    def _check_day_rollover(self):
        if core.rollover_tasks(self.data.tasks):
            self._save_timer.start()
            self._refresh_pages()
            self._sync_chrome()

    def show_about(self):
        AboutDialog(self).exec()

    def _on_week(self, week: int):
        self.week = week
        self.schedule_page.set_data(self.data, self.week)
        self._sync_chrome()

    # ------------------------------------------------------------ 课程
    def new_course(self, pref=None):
        pref = pref or {}
        default_day = int(pref.get("day") or core.date.today().isoweekday())
        default_period = int(pref.get("period") or 1)
        dlg = dialogs.CourseDialog(self, self.data, None, default_day, default_period)
        if dlg.exec():
            if dlg.result_course is not None:
                self.data.courses.append(dlg.result_course)
                self.data.sample = False
                self.commit()
                self.toast(f"已添加「{dlg.result_course.name}」", "ok")
            elif dlg.delete_requested:
                pass

    def edit_course(self, course):
        if course is None:
            return
        dlg = dialogs.CourseDialog(self, self.data, course, course.day, course.start)
        if not dlg.exec():
            return
        if dlg.delete_requested:
            self._delete_course(course)
            return
        result = dlg.result_course
        if result is None:
            return
        for i, c in enumerate(self.data.courses):
            if c.id == course.id:
                self.data.courses[i] = result
                break
        self.data.sample = False
        self.commit()
        self.toast("课程已保存", "ok")

    def _delete_course(self, course):
        if not widgets.ask_confirm(self, "删除课程", f"确定删除「{course.name}」吗？", "删除", True):
            return
        try:
            index = self.data.courses.index(course)
        except ValueError:
            return
        self.data.courses.pop(index)
        self.data.sample = False
        self.commit()
        self.toast("课程已删除", "warn", "撤销", lambda: self._restore_course(index, course))

    def _restore_course(self, index, course):
        self.data.courses.insert(min(index, len(self.data.courses)), course)
        self.commit()
        self.toast("已撤销删除", "ok")

    # ------------------------------------------------------------ 考试
    def new_exam(self):
        dlg = dialogs.ExamDialog(self, self.data, None)
        if dlg.exec() and dlg.result_exam is not None:
            self.data.exams.append(dlg.result_exam)
            self.data.sample = False
            self.commit()
            self.toast("考试已添加", "ok")

    def edit_exam(self, exam):
        if exam is None:
            return
        dlg = dialogs.ExamDialog(self, self.data, exam)
        if not dlg.exec():
            return
        if dlg.delete_requested:
            self._delete_exam(exam)
            return
        result = dlg.result_exam
        if result is None:
            return
        for i, e in enumerate(self.data.exams):
            if e.id == exam.id:
                self.data.exams[i] = result
                break
        self.data.sample = False
        self.commit()
        self.toast("考试已保存", "ok")

    def duplicate_exam(self, exam):
        if exam is None:
            return
        copy = core.Exam.from_dict(exam.to_dict()) if hasattr(core.Exam, "from_dict") else None
        if copy is None:
            copy = core.Exam(
                id=core.new_id("exam"), name=f"{exam.name}（副本）", type=exam.type,
                credits=exam.credits, date=exam.date, start_time=exam.start_time,
                duration=exam.duration, location=exam.location, seat=exam.seat,
                progress=exam.progress, note=exam.note,
                custom=[core.CustomField(f.label, f.value) for f in exam.custom],
                color=exam.color,
            )
        copy.id = core.new_id("exam")
        copy.name = f"{exam.name}（副本）"
        self.data.exams.append(copy)
        self.data.sample = False
        self.commit()
        self.toast("已复制考试，记得修改时间", "ok")

    def delete_exam(self, exam):
        if exam is None:
            return
        if not widgets.ask_confirm(self, "删除考试", f"确定删除「{exam.name}」吗？", "删除", True):
            return
        try:
            index = self.data.exams.index(exam)
        except ValueError:
            return
        self.data.exams.pop(index)
        self.data.sample = False
        self.commit()
        self.toast("考试已删除", "warn", "撤销", lambda: self._restore_exam(index, exam))

    def _restore_exam(self, index, exam):
        self.data.exams.insert(min(index, len(self.data.exams)), exam)
        self.commit()
        self.toast("已撤销删除", "ok")

    # ------------------------------------------------------------ 示例数据
    def _on_sample_action(self, action: str):
        if action == "clear":
            if not widgets.ask_confirm(self, "清空示例", "清空示例课程与考试，保留学期与作息设置？", "清空", True):
                return
            self.data.courses.clear()
            self.data.exams.clear()
            self.data.sample = False
            self.commit()
            self.toast("示例已清空，开始添加自己的课程吧", "ok")
        else:
            self.data.sample = False
            self.commit()
            self.toast("示例标记已移除", "ok")

    # ------------------------------------------------------------ 课表导入
    def open_import_dialog(self):
        """从课表选项卡打开「导入课表」对话框（lab 的识别能力）。

        对话框是模态的：识别 → 勾选 → 点「导入到课表」→ 写回 ``self.data``。
        """
        dialog = schedule_import.CourseImportDialog(self)
        dialog.applied.connect(self._on_import_applied)
        dialog.exec()

    def _on_import_applied(self, payload) -> None:
        try:
            added = schedule_import.apply_import(self.data, payload)
        except Exception as exc:  # noqa: BLE001 - 导入失败要提示，不能崩
            self.toast(f"导入失败：{exc}", "err")
            return
        self.commit()
        if added:
            self.toast(f"已导入 {added} 门课程", "ok")
        else:
            self.toast("没有新增课程（可能已经导入过）", "info")

    # ------------------------------------------------------------ 单词本
    def _on_wordbook_changed(self):
        # 单词本数据不进 data.json，只需保存它自己那份；refresh=False 避免
        # 重建课表 / 待办页抢焦点。
        self.commit(refresh=False)

    # ------------------------------------------------------------ 数据
    def export_json(self):
        default = str(Path.home() / f"课表备份-{date.today():%Y%m%d}.json")
        path, _ = QFileDialog.getSaveFileName(self, "导出备份", default, "JSON 文件 (*.json)")
        if not path:
            return
        try:
            core.export_data(self.data, path)
        except OSError as exc:
            self.toast(f"导出失败：{exc}", "err")
            return
        self.toast("备份已导出", "ok")

    def import_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入备份", str(Path.home()), "JSON 文件 (*.json)")
        if not path:
            return
        try:
            incoming = core.import_data(path)
        except (ValueError, OSError) as exc:
            self.toast(f"导入失败：{exc}", "err")
            return
        if not widgets.ask_confirm(self, "导入备份", "导入会覆盖当前课表与考试，确定继续吗？", "导入", False):
            return
        self.data = incoming
        self.week = core.current_week(self.data.settings.term_start,
                                      self.data.settings.total_weeks)
        self._save_now()
        self._refresh_pages()
        self.settings_page.set_data(self.data)
        self.go(0)
        self.toast("备份已导入", "ok")

    def export_ics(self):
        default = str(Path.home() / "课表日历.ics")
        path, _ = QFileDialog.getSaveFileName(self, "导出日历", default, "日历文件 (*.ics)")
        if not path:
            return
        try:
            core.export_ics(self.data, path)
        except OSError as exc:
            self.toast(f"导出失败：{exc}", "err")
            return
        self.toast("已导出，可导入手机日历", "ok")

    def open_data_dir(self):
        try:
            core.data_dir().mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.toast(f"无法创建数据目录：{exc}", "err")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(core.data_dir())))

    def load_sample(self):
        if not widgets.ask_confirm(self, "载入示例", "载入示例会覆盖当前数据，确定继续吗？", "载入", False):
            return
        self.data = core.sample_data()
        self.week = core.current_week(self.data.settings.term_start,
                                      self.data.settings.total_weeks)
        self._save_now()
        self._refresh_pages()
        self.settings_page.set_data(self.data)
        self.go(0)
        self.toast("示例数据已载入", "ok")

    def clear_all(self):
        if not widgets.ask_confirm(self, "清空全部数据", "将删除全部课程、考试与设置，且不可恢复。确定吗？",
                                   "全部清空", True):
            return
        self.data = core.AppData(
            version=core.DATA_VERSION, sample=False,
            settings=core.Settings(term_name=core.default_term_name()),
            periods=core.default_periods(), courses=[], exams=[],
            exam_types=list(core.DEFAULT_EXAM_TYPES),
        )
        self.week = core.current_week(self.data.settings.term_start,
                                      self.data.settings.total_weeks)
        self._save_now()
        self._refresh_pages()
        self.settings_page.set_data(self.data)
        self.go(0)
        self.toast("已清空，可以重新开始", "ok")

    # ------------------------------------------------------------ 杂项
    def toast(self, text: str, kind: str = "ok", action_label: str | None = None, on_action=None):
        self._toast.show_message(text, kind, action_label, on_action)

    def toggle_max(self):
        if self.windowState() & Qt.WindowState.WindowMaximized:
            self.setWindowState(Qt.WindowState.WindowNoState)
        else:
            self.setWindowState(Qt.WindowState.WindowMaximized)

    def _new_current(self):
        index = self.stack.currentIndex()
        if index == 3:
            self.new_exam()
        elif index == 2:
            self.todo_page.input.setFocus()
        else:
            self.new_course()

    def _key_week(self, delta: int):
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QComboBox, QAbstractSpinBox, QDateEdit, QTimeEdit)):
            return
        if self.stack.currentIndex() != 0:
            return
        self._on_week(core.clamp(self.week + delta, 1, self.data.settings.total_weeks))

    # 无边框窗口拖动边缘缩放
    def _edge_at(self, pos: QPoint) -> Qt.Edge:
        edge = Qt.Edge(0)
        m = 7
        if pos.x() <= m:
            edge |= Qt.Edge.LeftEdge
        elif pos.x() >= self.width() - m:
            edge |= Qt.Edge.RightEdge
        if pos.y() <= m:
            edge |= Qt.Edge.TopEdge
        elif pos.y() >= self.height() - m:
            edge |= Qt.Edge.BottomEdge
        return edge

    def mouseMoveEvent(self, event):
        if not (self.windowState() & Qt.WindowState.WindowMaximized):
            edge = self._edge_at(event.position().toPoint())
            cursors = {
                Qt.Edge.LeftEdge: Qt.CursorShape.SizeHorCursor,
                Qt.Edge.RightEdge: Qt.CursorShape.SizeHorCursor,
                Qt.Edge.TopEdge: Qt.CursorShape.SizeVerCursor,
                Qt.Edge.BottomEdge: Qt.CursorShape.SizeVerCursor,
                Qt.Edge.LeftEdge | Qt.Edge.TopEdge: Qt.CursorShape.SizeFDiagCursor,
                Qt.Edge.RightEdge | Qt.Edge.BottomEdge: Qt.CursorShape.SizeFDiagCursor,
                Qt.Edge.RightEdge | Qt.Edge.TopEdge: Qt.CursorShape.SizeBDiagCursor,
                Qt.Edge.LeftEdge | Qt.Edge.BottomEdge: Qt.CursorShape.SizeBDiagCursor,
            }
            self.setCursor(cursors.get(edge, Qt.CursorShape.ArrowCursor))
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self._edge_at(event.position().toPoint())
            if edge and not (self.windowState() & Qt.WindowState.WindowMaximized):
                wh = self.windowHandle()
                if wh is not None:
                    wh.startSystemResize(edge)
                event.accept()
                return
        super().mousePressEvent(event)

    def closeEvent(self, event):
        if self._save_timer.isActive():
            self._save_timer.stop()
        # 单词本页面可能还有后台线程 / 音频在跑，先停干净再退出
        if len(self._page_objs) > 5:
            page = self._page_objs[5]
            shutdown = getattr(page, "shutdown", None)
            if callable(shutdown):
                try:
                    shutdown()
                except Exception:  # noqa: BLE001 - 关窗时不要再抛错
                    pass
        try:
            core.save_data(self.data)
        except OSError:
            pass
        super().closeEvent(event)
