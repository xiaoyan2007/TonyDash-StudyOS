"""课表导入的中间数据模型。

刻意与两个世界都保持距离：

* 不直接构造主程序 ``Course`` —— 那样一旦主程序字段变动，导入层就崩；
* 也不照抄移动端的 ``startWeek/endWeek/weekType`` —— 那套模型表达不了
  ``3-4,6-10周``，必须拆课，属于信息损失。

中间模型用 ``(mode, weeks_text)`` 保存周次，导出时再翻译成任意目标格式。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from . import weeks as weeks_mod

WEEKDAY_CN = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "日"}
WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


@dataclass
class DraftCourse:
    """一门待导入的课程（用户可以逐条勾选、编辑）。"""

    name: str = ""
    teacher: str = ""
    location: str = ""
    day: int = 1                       # 1=周一 … 7=周日
    start: int = 1                     # 起始节次（1 起）
    end: int = 2                       # 结束节次（含）
    mode: str = "all"                  # all | odd | even | custom
    weeks_text: str = ""               # custom 时的 "1-8,10-16"
    parity: str = ""                   # "" | odd | even —— 文本里的「单周/双周」
    week_list: list[int] = field(default_factory=list)
    note: str = ""
    color: int = 0
    source: str = "manual"             # paste | csv | excel | ocr | manual
    confidence: float = 1.0
    raw: str = ""                      # 原始单元文本，便于排查
    issues: list[str] = field(default_factory=list)
    selected: bool = True

    # ------------------------------------------------------------------ 派生
    @property
    def weekday_name(self) -> str:
        return WEEKDAY_NAMES[max(0, min(6, int(self.day) - 1))]

    @property
    def periods_label(self) -> str:
        if self.start == self.end:
            return f"第 {self.start} 节"
        return f"第 {self.start}-{self.end} 节"

    def weeks_label(self, total: int = 0) -> str:
        result = weeks_mod.WeekResult(
            weeks=list(self.week_list), mode=self.mode,
            text=self.weeks_text, raw=self.weeks_text,
        )
        return result.label(total)

    @property
    def key(self) -> tuple:
        """去重键：同一天、同一节次、同名、同周次视为重复。"""
        return (
            self.name.strip(),
            int(self.day),
            int(self.start),
            int(self.end),
            self.mode,
            self.parity,
            (self.weeks_text or "").strip(),
        )

    # ------------------------------------------------------------------ 校验
    def validate(self, total: int = 0, clamp_period: int = 14) -> list[str]:
        """就地补齐 ``issues``，返回问题列表。"""
        issues: list[str] = []
        if not self.name.strip():
            issues.append("课程名为空")
        elif len(self.name.strip()) < 2:
            issues.append("课程名过短，可能是误识别")
        if not 1 <= int(self.day) <= 7:
            issues.append(f"星期超出范围：{self.day}")
        if self.start < 1 or self.end < 1:
            issues.append("节次必须为正数")
        if self.start > self.end:
            issues.append(f"起始节次大于结束节次（{self.start}>{self.end}）")
        if self.end > clamp_period:
            issues.append(f"节次 {self.end} 超出一天最大节数 {clamp_period}")
        if self.mode in ("odd", "even") and not self.week_list and total:
            self.week_list = sorted(weeks_mod.expand(self.mode, "", total))
        if self.mode == "custom" and not self.weeks_text and not self.week_list:
            issues.append("周次为空")
        if self.mode == "custom" and self.week_list and not self.weeks_text:
            self.weeks_text = weeks_mod.compress_ranges(self.week_list)
        # 保留 resolve_weeks 阶段留下的问题，别在二次校验时丢掉
        self.issues = list(dict.fromkeys(list(self.issues) + issues))
        return issues

    # ------------------------------------------------------------------ 导出
    def to_dict(self) -> dict:
        data = asdict(self)
        data["weekday"] = int(self.day)
        return data

    def to_core_kwargs(self) -> dict:
        """翻译成主程序 ``core.Course`` 的构造参数。

        字段名与 `campus_planner/core.py` 的 ``Course`` 一一对应，
        整合时直接 ``Course(**draft.to_core_kwargs())`` 即可。
        """
        mode = self.mode if self.mode in ("all", "odd", "even", "custom") else "custom"
        text = "" if mode != "custom" else (self.weeks_text or weeks_mod.compress_ranges(self.week_list))
        if mode == "custom" and self.parity in ("odd", "even") and self.week_list:
            # 整段周次都落在单（双）周上时改用主程序原生的 odd/even：
            # 免得将来学期总周数变了，自定义文本的语义跟着漂移
            native = weeks_mod.expand(self.parity, "", max(self.week_list))
            if set(self.week_list) <= native:
                mode = self.parity
                text = ""
        return {
            "name": self.name.strip(),
            "teacher": self.teacher.strip(),
            "location": self.location.strip(),
            "day": int(self.day),
            "start": int(self.start),
            "end": int(self.end),
            "weeks": {"mode": mode, "text": text},
            "color": int(self.color),
            "note": self.note.strip(),
        }


#: 只是「怎么归一的」说明，不算问题：进结果级 warnings，不进课程 issues
SOFT_NOTES = frozenset({
    "已按单/双周过滤周次。",
    "单双周信息已并入周次文本。",
})


@dataclass
class ImportResult:
    """一次导入的完整产物。"""

    courses: list[DraftCourse] = field(default_factory=list)
    source: str = ""
    total_weeks: int = 0
    periods: list[dict] = field(default_factory=list)   # [{period,start,end,startMinute,endMinute}]
    warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ 派生
    @property
    def selected(self) -> list[DraftCourse]:
        return [c for c in self.courses if c.selected]

    def finalize(self, *, clamp_period: int = 14) -> "ImportResult":
        """统一收尾：展开周次 → 推断学期总周数 → 回判 all/odd/even → 校验 → 去重。

        界面里用户每改一格都会重跑一次，所以这里必须**幂等**：问题与提示都要去重。
        """
        self.resolve_weeks()
        problems = 0
        for course in self.courses:
            problems += len(course.validate(self.total_weeks, clamp_period))
            course.issues = list(dict.fromkeys(course.issues))
        self.dedupe()
        self.sort_courses()
        self.warnings = list(dict.fromkeys(self.warnings))
        self.stats.update({
            "courses": len(self.courses),
            "selected": len(self.selected),
            "issues": problems,
        })
        return self

    def sort_courses(self) -> None:
        """按上课时间排序：周一第 1-2 节在最前，周日的课在最后。

        排序键 ``(星期, 起始节, 结束节, 课程名)``；星期不在 1~7 的异常行
        （例如 PDF 页脚没有节次信息的「实践课程」）排到最后，避免它们插进
        正常的工作日中间。``stable sort`` 保证同键课程保持原有相对顺序。
        """
        self.courses.sort(key=lambda c: (
            int(c.day) if 1 <= int(c.day) <= 7 else 8,
            int(c.start),
            int(c.end),
            c.name,
        ))

    def resolve_weeks(self) -> None:
        """把周次文本展开成具体周次，再用**整学期总周数**回判 all/odd/even。

        这一步是「不拆课」能成立的关键：先知道整学期多长，才能判断
        ``1-16周`` 到底是「全周」还是「只上前 16 周」；也只有这样，
        单双周才能被主程序原生识别，而不是塞一段字符串。
        """
        for course in self.courses:
            if course.mode == "custom" or course.parity:
                parsed = weeks_mod.parse_week_expr(
                    course.weeks_text or "", total=0, parity_hint=course.parity)
                if parsed.weeks:
                    course.week_list = parsed.weeks
                    for note in parsed.warnings:
                        # 只是「怎么归一的」说明，不算问题：放结果级提示里，
                        # 免得每门单双周课程都在预览里挂一个黄条。
                        if note in SOFT_NOTES:
                            self.warnings.append(note)
                        else:
                            course.issues.append(note)
                elif parsed.mode in ("odd", "even"):
                    # 只写了「单周/双周」没给范围：等总周数确定后再展开
                    course.mode = parsed.mode
                    course.weeks_text = ""
                    course.parity = ""
                else:
                    course.mode = "all"
                    course.weeks_text = ""
                    course.parity = ""
                    course.issues.append("没有周次信息，已按全周处理")
            elif course.mode in ("odd", "even"):
                course.week_list = []
            elif not course.week_list:
                # 这条记录压根没写周次：按全周上课，但要在预览里让用户看见
                course.issues.append("没有周次信息，已按全周处理")

        if not self.total_weeks:
            self.total_weeks = guess_total_weeks(self.courses)

        for course in self.courses:
            if course.mode in ("odd", "even"):
                course.week_list = sorted(weeks_mod.expand(course.mode, "", self.total_weeks))
            elif course.week_list:
                mode, text = weeks_mod.infer_mode(course.week_list, self.total_weeks)
                course.mode = mode
                course.weeks_text = text

    def dedupe(self) -> int:
        """按 ``key`` 去掉完全重复的行，返回删除条数。

        只在「周次集合真正相等」时合并，避免把前后八周同一门课误并成一条。
        """
        seen: dict[tuple, DraftCourse] = {}
        removed = 0
        for course in self.courses:
            key = course.key
            if key in seen:
                old = seen[key]
                old.week_list = sorted(set(old.week_list) | set(course.week_list))
                if old.mode == "custom" or course.mode == "custom":
                    old.mode = "custom"
                    old.weeks_text = weeks_mod.compress_ranges(old.week_list)
                removed += 1
                continue
            seen[key] = course
        if removed:
            self.courses = list(seen.values())
            self.warnings.append(f"合并了 {removed} 条重复课程。")
        return removed


def guess_total_weeks(courses) -> int:
    """从所有课程的最大周次推断学期总周数（至少 16，最多 30）。"""
    best = 0
    for course in courses:
        values = list(course.week_list or [])
        if course.mode == "all" and not values:
            values = [16]
        if values:
            best = max(best, max(values))
    if best <= 0:
        return 16
    return max(16, min(30, best))
