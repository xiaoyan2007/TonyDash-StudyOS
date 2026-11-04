"""词典查询 / 单词本 —— 把 lab 的 ``WordPage`` / ``WordbookPage`` 装进主程序。

这个文件是**主程序侧的外壳**：lab 的两个页面只知道「有一个 Kit 和一个
WordService」，不知道主程序的导航、主题切换和数据模型。外壳负责：

* 不加页头大标题，整块右侧区域全部留给功能本身（左栏已有导航名）；
* 懒加载一份 ``WordService``（查词页与单词本页共用同一份存储，收藏后立刻能查到）；
* 主程序切主题时重建页面（lab 页面把主题色写死在构造期，没有 ``sync_theme``）；
* 关窗时停后台线程，避免 QThread 被销毁时仍在运行。

**导航上查词与单词本是两个独立页面**（和 lab 原程序一致），共用一份词典存储。

数据存储位置由 ``labkit.common.paths`` 决定：``campus_planner/_data/``
（已进 .gitignore），不影响主程序课表 / 考试 / 待办的数据。
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from .. import core
from ..labkit.ui import Kit, WordPage, WordbookPage
from ..labkit.wordbook import api as wapi

__all__ = ["WordPageHost", "WordbookPageHost", "service", "close_service"]

#: 进程内唯一的词典服务。查词页与单词本页共用，收藏后立刻能在另一页看到。
_service: object | None = None


def service() -> object:
    """返回（必要时创建）全局唯一的 ``WordService``。"""
    global _service
    if _service is None:
        _service = wapi.make_service()
    return _service


def close_service() -> None:
    """关窗时释放词典服务持有的文件句柄。"""
    global _service
    if _service is not None:
        close = getattr(_service, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # noqa: BLE001 - 关窗时不要再抛错
                pass
        _service = None


class _WordbookShell(QWidget):
    """查词页 / 单词本页共用的外壳（不加页头，空间全留给功能）。"""

    #: 单词本内容变化（收藏 / 删除 / 备注 / 导入），供主窗口提示
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self.data: core.AppData | None = None
        self._kit = Kit()
        self._page: QWidget | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._page = self._make_page()
        self._page.setStyleSheet("background: transparent;")
        root.addWidget(self._page, 1)

    # -- 子类实现
    def _make_page(self) -> QWidget:
        raise NotImplementedError

    # -- 数据
    def set_data(self, data, *args) -> None:
        """主程序的数据入口（课表 / 考试 / 待办对本页无用，只留作以后扩展）。"""
        self.data = data

    def refresh(self) -> None:
        """主窗口 commit 后刷新一次。"""
        fn = getattr(self._page, "refresh", None)
        if callable(fn):
            try:
                fn()
            except Exception:  # noqa: BLE001 - 刷新失败不该影响其他页
                pass

    # -- 主题
    def sync_theme(self) -> None:
        """lab 页面没有 ``sync_theme``，只能整页重建才能跟随主程序切主题。"""
        self.stop()
        old = self._page
        self._page = self._make_page()
        self._page.setStyleSheet("background: transparent;")
        root = self.layout()
        index = root.indexOf(old)
        root.removeWidget(old)
        old.setParent(None)
        old.deleteLater()
        if index < 0:
            index = root.count()
        root.insertWidget(index, self._page, 1)

    # -- 清理
    def stop(self) -> None:
        """停掉后台线程与音频，避免切页 / 关窗时 QThread 还在跑。"""
        self._stop_page(self._page)

    def shutdown(self) -> None:
        """关窗：停后台线程。词典服务是进程内共享的，由 :func:`close_service` 统一释放。"""
        self.stop()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self.stop()
        super().closeEvent(event)

    @staticmethod
    def _stop_page(page) -> None:
        if page is None:
            return
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


class WordPageHost(_WordbookShell):
    """词典查询页（独立导航项）。"""

    def _make_page(self) -> QWidget:
        return WordPage(service(), kit=self._kit)


class WordbookPageHost(_WordbookShell):
    """单词本页（独立导航项，与查词页共用同一份存储）。"""

    def _make_page(self) -> QWidget:
        return WordbookPage(service(), kit=self._kit)
