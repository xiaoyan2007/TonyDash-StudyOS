"""课表导入对话框 —— 把 lab 的课表识别能力接进主程序的课表选项卡。

为什么单独一个文件
------------------
``labkit.ui.ImportPage`` 是从 lab 原样搬过来的识别界面，它只负责「选文件 /
粘贴文本 / 识别截图 / 预览勾选」，**不碰主程序的数据模型**。这个模块负责两件事：

1. 用主程序的 ``GlassDialog`` 把它装起来（视觉与主程序一致）；
2. 把 ``applied`` 载荷翻译成 :class:`campus_planner.core.Course` /
   :class:`campus_planner.core.Period`，写进 :class:`core.AppData`。

这样 ``labkit`` 里没有一行代码依赖主程序的数据结构，回滚时只要删掉这个文件。
"""

from __future__ import annotations

from PySide6.QtCore import Signal

from . import core
from .labkit.ui import ImportPage
from .labkit.ui.kit import Kit
from .widgets import GlassDialog

# ``api.parse_many`` 只在真正调用时才懒加载 ``merge``，而它跑在后台线程里；
# 新拷贝的文件首次读取可能被系统实时扫描拖慢数秒，界面会一直停在「准备中…」。
# 这里在主进程启动时就先导入，让首次打开对话框不必付这笔钱。
from .labkit.ttimport import merge as _merge  # noqa: F401 - 仅为预导入

__all__ = ["CourseImportDialog", "apply_import", "to_courses"]


def to_courses(items, total_weeks: int = 0) -> list[core.Course]:
    """把 ``ImportPage.applied`` 里的课程载荷转成 :class:`core.Course`。

    字段映射与 :func:`core._course_from_dict` 保持一致（同样的裁剪与兜底），
    但走的是 lab 侧的 ``to_core_kwargs()`` 字段名。
    """
    courses: list[core.Course] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()[:60]
        if not name:
            continue
        try:
            day = core.clamp(int(item.get("day") or 1), 1, 7)
            start = max(1, int(item.get("start") or 1))
            end = max(start, int(item.get("end") or start))
        except (TypeError, ValueError):
            day, start, end = 1, 1, 2
        weeks = core.WeekSpec.from_dict(item.get("weeks"))
        if weeks.mode == "custom" and not core.parse_weeks_text(weeks.text, total_weeks):
            # 自定义周次文本为空 / 全是非法段时，退回整学期，避免一周课都不显示
            weeks = core.WeekSpec("all", "")
        try:
            color = core.clamp(int(item.get("color") or 1), 1, 8)
        except (TypeError, ValueError):
            color = 1
        courses.append(core.Course(
            id=core.new_id("c"),
            name=name,
            teacher=str(item.get("teacher") or "").strip()[:40],
            location=str(item.get("location") or "").strip()[:40],
            day=day, start=start, end=end, weeks=weeks, color=color,
            note=str(item.get("note") or "").strip()[:300],
        ))
    return courses


def apply_import(data: core.AppData, payload: dict) -> int:
    """把一份 ``applied`` 载荷写进 ``data``，返回**新增**的课程数。

    已存在的「同一天 + 同一节次 + 同名」课程不会被重复添加（识别结果里
    同一门课可能因为换了张截图而再出现一次）；作息表按 ``(start, end)`` 去重。
    """
    total = int(payload.get("total_weeks") or 0)
    existing = {(c.name.strip(), int(c.day), int(c.start), int(c.end)) for c in data.courses}
    added = 0
    for course in to_courses(payload.get("courses"), total):
        key = (course.name, course.day, course.start, course.end)
        if key in existing:
            continue
        data.courses.append(course)
        existing.add(key)
        added += 1

    known = {(p.start, p.end) for p in data.periods}
    for item in payload.get("periods") or []:
        if not isinstance(item, dict):
            continue
        start = core.norm_hhmm(str(item.get("start") or ""), fallback="")
        end = core.norm_hhmm(str(item.get("end") or ""), fallback="")
        if not start or not end or (start, end) in known:
            continue
        data.periods.append(core.Period(start, end))
        known.add((start, end))

    if total and total != data.settings.total_weeks:
        # 识别出来的学期总周数比设置的更准确时，用识别结果（用户仍可在设置里改）
        data.settings.total_weeks = total
    return added


class CourseImportDialog(GlassDialog):
    """在主程序的对话框里装一个 ``ImportPage``。

    点「导入到课表」→ 发出 ``applied``（载荷见 :func:`apply_import`）并关闭。
    """

    applied = Signal(object)

    def __init__(self, parent=None, width: int = 760):
        super().__init__(
            parent, width=width,
            title="导入课表",
            subtitle="Excel / CSV / 截图 / 粘贴文本都能识别，勾选后一键导入",
            icon="upload",
        )
        self._page = ImportPage(Kit(), toast=None)
        # GlassDialog 已经把卡片分成 head / error / body / footer，
        # 识别页直接塞进 body，标题栏和关闭按钮都由它自己提供。
        self.body_layout.addWidget(self._page)
        self._page.applied.connect(self._on_applied)

    def _on_applied(self, payload) -> None:
        self.applied.emit(payload)
        self.accept()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        # 页面可能正在跑 OCR / PDF 解析，关掉窗口时把后台线程停掉
        self._page.stop()
        super().closeEvent(event)
