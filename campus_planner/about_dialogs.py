"""关于、更新日志与待办完成历史弹窗。"""
from __future__ import annotations

import os
import subprocess

from PySide6.QtCore import QDate, Qt, QUrl
from PySide6.QtGui import (
    QColor, QDesktopServices, QPainter, QPainterPath, QPalette, QPixmap,
    QTextCharFormat,
)
from PySide6.QtWidgets import (
    QCalendarWidget, QGridLayout, QHBoxLayout, QLabel, QMessageBox,
    QTextBrowser, QVBoxLayout, QWidget,
)

from . import changelog, core, theme, widgets


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _round_pixmap(path: str, size: int, radius: float | None = None) -> QPixmap:
    source = QPixmap(path)
    if source.isNull():
        pm = QPixmap(size, size)
        pm.fill(QColor(theme.C_BLUE))
        return pm
    scaled = source.scaled(
        size, size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    out = QPixmap(size, size)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    shape = QPainterPath()
    r = size / 2 if radius is None else radius
    shape.addRoundedRect(0, 0, size, size, r, r)
    p.setClipPath(shape)
    p.drawPixmap((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
    p.end()
    return out


class _GithubCard(QWidget):
    """头像 + GitHub Logo + 主页地址，整块可点击。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("githubCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._apply_style()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setSpacing(10)
        avatar = QLabel(self)
        avatar.setPixmap(_round_pixmap(theme.asset_path("github_avatar.png"), 44))
        avatar.setFixedSize(44, 44)
        lay.addWidget(avatar)

        col = QVBoxLayout()
        col.setSpacing(1)
        name = QLabel(core.APP_AUTHOR, self)
        name.setFont(theme.font(12.5, theme.QFont.Weight.DemiBold))
        name.setStyleSheet(f"color: {theme.C_TEXT}; background: transparent;")
        sub = QLabel("github.com/xiaoyan2007", self)
        sub.setFont(theme.font(11))
        sub.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        col.addWidget(name)
        col.addWidget(sub)
        lay.addLayout(col, 1)

        logo = QLabel(self)
        logo.setPixmap(_round_pixmap(theme.asset_path("github_logo.png"), 24, 5))
        logo.setFixedSize(24, 24)
        lay.addWidget(logo)
        arrow = widgets.IconLabel("external", 13, theme.C_SUB, self)
        lay.addWidget(arrow)
        for child in (avatar, name, sub, logo, arrow):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def _apply_style(self):
        dark = theme.MODE == "dark"
        bg = "rgba(46, 52, 70, 170)" if dark else "rgba(255, 255, 255, 150)"
        bg_hover = "rgba(60, 68, 92, 214)" if dark else "rgba(255, 255, 255, 214)"
        border = "rgba(255, 255, 255, 60)" if dark else "rgba(255, 255, 255, 224)"
        self.setStyleSheet(
            "#githubCard { background: " + bg + ";"
            " border: 1px solid " + border + "; border-radius: 13px; }"
            "#githubCard:hover { background: " + bg_hover + "; }"
        )

    def open_github(self):
        """打开项目主页：openUrl 优先，失败时回退到系统打开方式。"""
        url = core.APP_GITHUB
        opened = False
        try:
            opened = bool(QDesktopServices.openUrl(QUrl(url)))
        except Exception:
            opened = False
        if not opened:
            try:
                if os.name == "nt":
                    os.startfile(url)  # type: ignore[attr-defined]
                else:
                    subprocess.Popen(["xdg-open", url])
                opened = True
            except Exception:
                opened = False
        if not opened:
            QMessageBox.information(
                self, "无法打开浏览器",
                f"请手动在浏览器中打开：\n{url}",
            )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_github()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            return
        super().mouseReleaseEvent(event)


class ChangelogDialog(widgets.GlassDialog):
    def __init__(self, parent=None):
        super().__init__(
            parent, width=620, title="更新日志",
            subtitle="全部版本更新记录，当前版本在最上方",
            icon="spark",
        )
        browser = QTextBrowser(self.body)
        browser.setOpenExternalLinks(True)
        browser.setMinimumHeight(496)
        browser.setStyleSheet("QTextBrowser { background: transparent; border: none; }")
        browser.setHtml(changelog.changelog_html())
        self.body_layout.addWidget(browser)
        self.add_footer_stretch()
        ok = widgets.AppButton("关闭", None, "primary", "md")
        ok.clicked.connect(self.accept)
        self.add_footer(ok, stretch_before=False)
        self.setMinimumHeight(660)
        self.resize(676, 660)


class AboutDialog(widgets.GlassDialog):
    def __init__(self, parent=None):
        super().__init__(parent, width=486, title="关于 TonyDash", icon="info")
        self.subtitle_label.hide()

        hero = QHBoxLayout()
        hero.setSpacing(13)
        icon = QLabel(self.body)
        icon.setPixmap(theme.app_icon(72).pixmap(72, 72))
        icon.setFixedSize(72, 72)
        hero.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(2)
        name = QLabel(core.APP_NAME, self.body)
        name.setFont(theme.font(20, theme.QFont.Weight.DemiBold))
        name.setStyleSheet(f"color: {theme.C_TEXT}; background: transparent;")
        slogan = QLabel(core.APP_SLOGAN, self.body)
        slogan.setFont(theme.font(12))
        slogan.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        slogan.setWordWrap(True)
        version = QLabel(f"{core.APP_VERSION}  ·  {core.APP_RELEASE_DATE}", self.body)
        version.setFont(theme.font(11.5, theme.QFont.Weight.DemiBold))
        version.setStyleSheet(f"color: {theme.C_BLUE}; background: transparent;")
        text.addWidget(name)
        text.addWidget(slogan)
        text.addWidget(version)
        hero.addLayout(text, 1)
        self.body_layout.addLayout(hero)

        info = widgets.GlassCard(radius=13, alpha=112)
        grid = QGridLayout(info)
        grid.setContentsMargins(14, 11, 14, 11)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(7)
        rows = (
            ("版本", core.APP_VERSION),
            ("发布日期", core.APP_RELEASE_DATE),
            ("开发者", core.APP_AUTHOR),
            ("数据格式", f"v{core.DATA_VERSION} · 本地保存，不联网"),
        )
        for row, (key, value) in enumerate(rows):
            k = widgets.label(key, 11.5)
            v = widgets.label(value, 12)
            v.setFont(theme.font(12, theme.QFont.Weight.DemiBold))
            grid.addWidget(k, row, 0)
            grid.addWidget(v, row, 1)
        grid.setColumnStretch(1, 1)
        self.body_layout.addWidget(info)

        self.body_layout.addWidget(_GithubCard(self.body))

        latest = changelog.latest()
        recent_title = QLabel(f"最近更新 · {latest.version}", self.body)
        recent_title.setFont(theme.font(11, theme.QFont.Weight.DemiBold))
        recent_title.setStyleSheet(f"color: {theme.C_TEXT}; background: transparent;")
        self.body_layout.addWidget(recent_title)

        bullets = QLabel(self.body)
        bullets.setWordWrap(True)
        bullets.setTextFormat(Qt.TextFormat.RichText)
        bullets.setFont(theme.font(12))
        colors = {
            "新增": theme.C_GREEN, "变更": theme.C_BLUE, "修复": theme.C_AMBER,
        }
        lines = []
        for item in changelog.latest_summary(4, balanced=True):
            tag, _, rest = item.partition(" · ")
            color = colors.get(tag, theme.C_SUB)
            lines.append(
                f'<div style="margin:2px 0;"><span style="color:{color};">{_esc(tag)}'
                f'</span><span style="color:{theme.C_TEXT};"> · {_esc(rest)}</span></div>'
            )
        bullets.setText("".join(lines))
        bullets.setStyleSheet(f"color: {theme.C_TEXT}; background: transparent;")
        self.body_layout.addWidget(bullets)

        tribute = QLabel(
            "关于界面结构、更新日志写法参考「拾光 ShiGuang」V0.2（作者 yyx，© 2026 yyx），在此致谢。",
            self.body,
        )
        tribute.setWordWrap(True)
        tribute.setFont(theme.font(11))
        tribute.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        self.body_layout.addWidget(tribute)

        self.add_footer_stretch()
        log_btn = widgets.AppButton("查看完整更新日志", None, "white", "md")
        log_btn.clicked.connect(self._show_changelog)
        ok = widgets.AppButton("好的", None, "primary", "md")
        ok.clicked.connect(self.accept)
        self.add_footer(log_btn, stretch_before=False)
        self.add_footer(ok, stretch_before=False)
        # 顶层窗口默认高度会被限制在屏幕的 2/3，内容比这高时 Qt 会把卡片压扁、
        # 文字被裁掉。这里显式按内容最小高度撑开（屏幕放不下时再退回可用高度）。
        _avail = 0
        _screen = self.screen()
        if _screen is not None:
            _avail = _screen.availableGeometry().height() - 40
        _need = self.sizeHint().height()
        self.setMinimumHeight(min(_need, _avail) if _avail > 400 else _need)

    def _show_changelog(self):
        ChangelogDialog(self.parent()).exec()


class TaskHistoryDialog(widgets.GlassDialog):
    def __init__(self, parent, task: core.Task):
        count = len(task.history)
        latest = max(task.history.values()) if task.history else ""
        latest_text = latest.replace("T", " ")[:16] if latest else "尚无记录"
        super().__init__(parent, width=460, title=task.text[:26], icon="calendar")
        self.subtitle_label.setText(f"共完成 {count} 次 · 最近：{latest_text}")
        self.subtitle_label.setVisible(True)

        cal = QCalendarWidget(self.body)
        cal.setGridVisible(False)
        cal.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        cal.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        cal.setMinimumHeight(300)
        cal.setMaximumHeight(320)
        t = theme.tokens()
        card_bg = theme.card_rgba(250)
        card_alt = theme.rgba_str(t["card"], 238)
        text_col = theme.C_TEXT
        blue_col = theme.C_BLUE
        cal.setStyleSheet(f"""
            QCalendarWidget QWidget {{ background: {card_bg}; color: {text_col}; }}
            QCalendarWidget QWidget#qt_calendar_navigationbar {{ background: {card_bg}; }}
            QCalendarWidget QToolButton {{
                color: {text_col}; background: transparent; border: none;
                border-radius: 6px; padding: 3px 8px;
            }}
            QCalendarWidget QToolButton:hover {{ background: rgba(10,132,255,24); }}
            QCalendarWidget QMenu {{ background: {card_bg}; color: {text_col}; }}
            QCalendarWidget QSpinBox {{
                background: {card_bg}; color: {text_col};
                border: 1px solid rgba(28,28,30,28); border-radius: 6px;
            }}
            QCalendarWidget QAbstractItemView:enabled {{
                background: {card_bg}; color: {text_col};
                selection-background-color: {blue_col}; selection-color: #FFFFFF;
                outline: 0;
            }}
            QCalendarWidget QAbstractItemView:disabled {{ color: {theme.C_MUTED}; }}
            QCalendarWidget QTableView {{ background: {card_bg}; border: none; }}
            QCalendarWidget QHeaderView::section {{
                background: {card_bg}; color: {theme.C_MUTED}; border: none; padding: 4px 0;
            }}
        """)
        palette = cal.palette()
        for role, value in (
            (QPalette.ColorRole.Window, card_bg),
            (QPalette.ColorRole.Base, card_bg),
            (QPalette.ColorRole.AlternateBase, card_alt),
            (QPalette.ColorRole.Text, text_col),
            (QPalette.ColorRole.WindowText, text_col),
            (QPalette.ColorRole.ButtonText, text_col),
            (QPalette.ColorRole.Highlight, blue_col),
            (QPalette.ColorRole.HighlightedText, "#FFFFFF"),
        ):
            palette.setColor(role, theme.qcolor(value))
        cal.setPalette(palette)

        header_fmt = QTextCharFormat()
        header_fmt.setForeground(QColor(theme.C_TEXT))
        header_fmt.setBackground(theme.qcolor(theme.card_rgba(240)))
        cal.setHeaderTextFormat(header_fmt)

        fmt = QTextCharFormat()
        fmt.setBackground(QColor(theme.C_GREEN))
        fmt.setForeground(QColor("#FFFFFF"))
        for text in task.history:
            try:
                y, m, d = (int(x) for x in text.split("-"))
                cal.setDateTextFormat(QDate(y, m, d), fmt)
            except (ValueError, TypeError):
                continue

        if task.deadline:
            due_fmt = QTextCharFormat()
            due_fmt.setBackground(QColor("#FF9F0A"))
            due_fmt.setForeground(QColor("#FFFFFF"))
            try:
                y, m, d = (int(x) for x in task.deadline.split("-"))
                cal.setDateTextFormat(QDate(y, m, d), due_fmt)
                cal.setSelectedDate(QDate(y, m, d))
            except (ValueError, TypeError):
                pass

        self.body_layout.addWidget(cal)

        legend = QLabel("● 绿色为完成日期 · 琥珀为截止日期 · 点击日期可直接查看", self.body)
        legend.setFont(theme.font(11))
        legend.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        legend.setWordWrap(True)
        self.body_layout.addWidget(legend)

        self.add_footer_stretch()
        ok = widgets.AppButton("关闭", None, "primary", "md")
        ok.clicked.connect(self.accept)
        self.add_footer(ok, stretch_before=False)
        self.resize(486, 540)
