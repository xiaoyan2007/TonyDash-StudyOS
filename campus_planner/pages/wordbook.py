"""词典 · 单词本 —— 把 lab 的 ``WordPage`` / ``WordbookPage`` 装进主程序。

这个文件是**主程序侧的外壳**：lab 的两个页面只知道「有一个 Kit 和一个
WordService」，不知道主程序的导航、主题切换和数据模型。外壳负责：

* 建一套和主程序一致的页面头与子导航（查词 / 单词本）；
* 懒加载一份 ``WordService``（查词页与单词本页共用同一份存储，收藏后立刻能查到）；
* 主程序切主题时重建两个页面（lab 页面把主题色写死在构造期，没有 ``sync_theme``）。

数据存储位置由 ``labkit.common.paths`` 决定：``campus_planner/_data/``
（已进 .gitignore），不影响主程序课表 / 考试 / 待办的数据。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import core, widgets
from ..labkit.ui import Kit, WordPage, WordbookPage
from ..labkit.wordbook import api as wapi
from . import common

__all__ = ["WordbookPageHost"]


class WordbookPageHost(QWidget):
    """查词 + 单词本，装在一个页面里。"""

    #: 单词本内容变化（收藏 / 删除 / 备注 / 导入），供主窗口提示
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self.data: core.AppData | None = None
        self._kit = Kit()
        self._service: object | None = None
        self._page_objs: dict[str, QWidget] = {}
        self._current = "word"
        self._build()
        self._switch("word")

    # ------------------------------------------------------------------ 构建
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        self.header = common.PageHeader(
            "", "词典 · 单词本",
            hint="输入单词查询释义，收藏后自动进入单词本；支持导出 / 导入 JSON")
        root.addWidget(self.header)

        bar_card = widgets.GlassCard(radius=12, alpha=128)
        bar = QHBoxLayout(bar_card)
        bar.setContentsMargins(8, 5, 8, 5)
        bar.setSpacing(8)

        self.sub_group = QButtonGroup(self)
        self.sub_group.setExclusive(True)
        self.sub_buttons: dict[str, widgets.AppButton] = {}
        for key, label, icon, kind in (("word", "查词", "search", "soft"),
                                      ("book", "单词本", "star", "ghost")):
            button = widgets.AppButton(label, icon, kind, "sm")
            button.setCheckable(True)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(lambda _=False, k=key: self._switch(k))
            self.sub_group.addButton(button)
            self.sub_buttons[key] = button
            bar.addWidget(button)
        bar.addStretch(1)
        self.status_chip = widgets.Chip("", "neutral")
        bar.addWidget(self.status_chip)
        root.addWidget(bar_card)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background: transparent;")
        root.addWidget(self.stack, 1)

    # ------------------------------------------------------------------ 服务
    def service(self):
        """词典服务（懒单例：首次切到任一子页时才建）。"""
        if self._service is None:
            self._service = wapi.make_service()
        return self._service

    def _make_page(self, key: str) -> QWidget:
        if key == "book":
            return WordbookPage(self.service(), kit=self._kit)
        return WordPage(self.service(), kit=self._kit)

    # ------------------------------------------------------------------ 切换
    def _switch(self, key: str) -> None:
        if key not in ("word", "book"):
            key = "word"
        if key not in self._page_objs:
            page = self._make_page(key)
            page.setStyleSheet("background: transparent;")
            self._page_objs[key] = page
            self.stack.addWidget(page)
        self._current = key
        self.stack.setCurrentWidget(self._page_objs[key])
        for name, button in self.sub_buttons.items():
            button.setChecked(name == key)
        self._update_status()

    def set_data(self, data, *args) -> None:
        """主程序的数据入口（课表 / 考试 / 待办对本页无用，只留作以后扩展）。"""
        self.data = data

    def refresh(self) -> None:
        """主窗口 commit 后刷新一次（单词本页重载列表；查词页保留结果）。"""
        for page in self._page_objs.values():
            fn = getattr(page, "refresh", None)
            if callable(fn):
                try:
                    fn()
                except Exception:  # noqa: BLE001 - 刷新失败不该影响其他页
                    pass
        self._update_status()

    def sync_theme(self) -> None:
        """lab 页面没有 ``sync_theme``，只能整页重建才能跟随主程序切主题。"""
        current = self._current
        self._stop_pages()
        for page in self._page_objs.values():
            self.stack.removeWidget(page)
            page.setParent(None)
            page.deleteLater()
        self._page_objs.clear()
        self._switch(current)

    # ------------------------------------------------------------------ 清理
    def stop(self) -> None:
        """停掉后台线程与音频，避免切页 / 关窗时 QThread 还在跑。"""
        self._stop_pages()

    def shutdown(self) -> None:
        """关窗：停后台线程并释放词典服务持有的文件句柄。"""
        self.stop()
        service = self._service
        if service is not None:
            close = getattr(service, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # noqa: BLE001 - 关窗时不要再抛错
                    pass
            self._service = None

    def _stop_pages(self) -> None:
        for page in self._page_objs.values():
            self._stop_page(page)

    @staticmethod
    def _stop_page(page) -> None:
        for attr in ("_worker", "_save_worker"):
            worker = getattr(page, attr, None)
            if worker is not None and worker.isRunning():
                try:
                    worker.quit()
                    worker.wait(1000)
                except Exception:  # noqa: BLE001 - 关窗时不要再抛错
                    pass
        audio = getattr(page, "audio", None)
        if audio is not None:
            fn = getattr(audio, "stop", None)
            if callable(fn):
                try:
                    fn()
                except Exception:  # noqa: BLE001 - 关窗时不要再抛错
                    pass
        stop = getattr(page, "stop", None)
        if callable(stop):
            try:
                stop()
            except Exception:  # noqa: BLE001 - 关窗时不要再抛错
                pass

    # ------------------------------------------------------------------ 杂项
    def _update_status(self) -> None:
        try:
            text = wapi.status_text(self.service())
        except Exception:  # noqa: BLE001 - 服务还没建好时不显示
            text = ""
        self.status_chip.setText(text)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self.stop()
        super().closeEvent(event)
