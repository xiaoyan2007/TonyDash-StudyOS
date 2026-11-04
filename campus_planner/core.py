"""课表 · 期末 —— 本科生学业面板。

核心层：数据模型、周次计算、冲突检测、持久化与日历导出。
这一层不依赖 Qt，方便直接跑单元测试。
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

APP_NAME = "TonyDash学习终端"
APP_SUBTITLE = "课表 · 考试 · 待办"
APP_VERSION = "Beta 1.5"
APP_SLOGAN = "把课表、考试和待办，收进一块玻璃里"
APP_AUTHOR = "xiaoyan2007"
APP_GITHUB = "https://github.com/xiaoyan2007"
APP_RELEASE_DATE = "2026-11-04"
DATA_VERSION = 3
STORE_DIR_NAME = "CampusPlanner"
STORE_FILE_NAME = "data.json"

DAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
SHORT_DAYS = ["一", "二", "三", "四", "五", "六", "日"]

DEFAULT_PERIODS = [
    ("08:05", "08:50"), ("08:50", "09:35"), ("09:50", "10:35"), ("10:40", "11:25"),
    ("11:30", "12:15"), ("13:40", "14:25"), ("14:35", "15:20"), ("15:30", "16:15"),
    ("16:25", "17:10"), ("18:30", "19:15"), ("19:25", "20:10"), ("20:20", "21:05"),
]

DEFAULT_EXAM_TYPES = ["闭卷", "开卷", "机考", "大作业", "口试", "论文"]

TASK_TYPES = ("daily", "weekly", "once")
TASK_TYPE_LABELS = {"daily": "每日", "weekly": "每周", "once": "一次"}

WEEK_MODES = ("all", "odd", "even", "custom")
WEEK_MODE_LABELS = {"all": "每周", "odd": "单周", "even": "双周", "custom": "自定义"}

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def new_id(prefix: str) -> str:
    return prefix + uuid.uuid4().hex[:8]


def clamp(value, low, high):
    return max(low, min(high, value))


def valid_time(text: str) -> bool:
    return bool(_TIME_RE.match(str(text or "").strip()))


def norm_hhmm(text: str, fallback: str = "08:00") -> str:
    """把 '8:5' 之类的输入规整成 '08:05'；非法则回退。"""
    text = str(text or "").strip()
    m = _TIME_RE.match(text)
    if not m:
        m2 = re.match(r"^(\d{1,2}):(\d{1,2})$", text)
        if not m2:
            return fallback
        h, mi = int(m2.group(1)), int(m2.group(2))
        if not (0 <= h <= 23 and 0 <= mi <= 59):
            return fallback
        return f"{h:02d}:{mi:02d}"
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def time_to_minutes(text: str) -> int:
    t = norm_hhmm(text)
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def minutes_to_time(minutes: int) -> str:
    minutes = int(minutes) % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def ranges_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def default_term_name(day: date | None = None) -> str:
    """按日期推断学期名，形如「2026-2027学年第1学期」。"""
    d = day or date.today()
    if d.month >= 8:
        year, part = d.year, 1
    elif d.month <= 1:
        year, part = d.year - 1, 1
    else:
        year, part = d.year - 1, 2
    return f"{year}-{year + 1}学年第{part}学期"


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def format_cn_date(day: date) -> str:
    return f"{day.month} 月 {day.day} 日"


def format_weekday(day: date) -> str:
    return DAY_NAMES[day.weekday()]


def format_short_range(d1: date, d2: date) -> str:
    if d1.year != d2.year:
        return f"{d1.year}/{d1.month}/{d1.day} – {d2.year}/{d2.month}/{d2.day}"
    if d1.month == d2.month:
        return f"{d1.month} 月 {d1.day} – {d2.day} 日"
    return f"{d1.month} 月 {d1.day} 日 – {d2.month} 月 {d2.day} 日"


# --------------------------------------------------------------------------
# 周次
# --------------------------------------------------------------------------
@dataclass
class WeekSpec:
    mode: str = "all"
    text: str = ""

    def to_dict(self) -> dict:
        return {"mode": self.mode, "text": self.text}

    @classmethod
    def from_dict(cls, raw) -> "WeekSpec":
        if isinstance(raw, WeekSpec):
            return WeekSpec(raw.mode, raw.text)
        if isinstance(raw, (list, tuple)):
            # 兼容早期直接写成周次数组的备份：保留成自定义周次，而不是整学期。
            text = ",".join(str(x).strip() for x in raw if str(x).strip())
            return WeekSpec("custom", text)
        if isinstance(raw, dict):
            mode = str(raw.get("mode") or "all").strip().lower()
            text = str(raw.get("text") or "").strip()
            if mode not in WEEK_MODES:
                # 模式名坏掉但周次文本还在时，按自定义周次处理，避免整学期被悄悄放大。
                mode = "custom" if text else "all"
            return WeekSpec(mode, text)
        if isinstance(raw, str):
            return WeekSpec("custom", raw)
        return WeekSpec()


def parse_weeks_text(text: str, total: int) -> list[int]:
    """解析 '1-8,10-16'、'1、3、5' 这类周次文本。"""
    total = clamp(int(total or 18), 1, 30)
    found: set[int] = set()
    for token in re.split(r"[,，、;；\s]+", str(text or "").strip()):
        if not token:
            continue
        m = re.fullmatch(r"(\d+)\s*[-~–—]\s*(\d+)", token)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a > b:
                a, b = b, a
            for n in range(a, b + 1):
                if 1 <= n <= total:
                    found.add(n)
            continue
        if token.isdigit():
            n = int(token)
            if 1 <= n <= total:
                found.add(n)
    return sorted(found)


def expand_weeks(spec: WeekSpec | dict | str, total: int) -> set[int]:
    total = clamp(int(total or 18), 1, 30)
    if not isinstance(spec, WeekSpec):
        spec = WeekSpec.from_dict(spec)
    if spec.mode == "all":
        return set(range(1, total + 1))
    if spec.mode == "odd":
        return set(range(1, total + 1, 2))
    if spec.mode == "even":
        return set(range(2, total + 1, 2))
    return set(parse_weeks_text(spec.text, total))


def compress_ranges(numbers) -> str:
    nums = sorted({int(n) for n in numbers})
    if not nums:
        return ""
    parts: list[str] = []
    start = prev = nums[0]
    for n in nums[1:]:
        if n == prev + 1:
            prev = n
            continue
        parts.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = n
    parts.append(str(start) if start == prev else f"{start}-{prev}")
    return ",".join(parts)


def weeks_label(spec: WeekSpec | dict | str, total: int) -> str:
    if not isinstance(spec, WeekSpec):
        spec = WeekSpec.from_dict(spec)
    if spec.mode == "all":
        return f"1-{clamp(int(total or 18), 1, 30)} 周"
    if spec.mode == "odd":
        return "单周"
    if spec.mode == "even":
        return "双周"
    text = compress_ranges(parse_weeks_text(spec.text, total))
    return (text + " 周") if text else "未设置周次"


def date_of_week_day(term_start: date, week: int, day: int) -> date:
    """term_start 为第 1 周周一；day 取 1..7。"""
    return term_start + timedelta(days=(int(week) - 1) * 7 + (int(day) - 1))


def current_week(term_start: date, total: int, today: date | None = None) -> int:
    d = today or date.today()
    diff = (d - term_start).days
    week = diff // 7 + 1
    return clamp(week, 1, clamp(int(total or 18), 1, 30))


# --------------------------------------------------------------------------
# 数据模型
# --------------------------------------------------------------------------
@dataclass
class Period:
    start: str = "08:00"
    end: str = "08:45"

    def to_dict(self) -> dict:
        return {"start": self.start, "end": self.end}


def default_periods() -> list[Period]:
    """默认 12 节作息，返回新的 Period 列表。"""
    return [Period(s, e) for s, e in DEFAULT_PERIODS]


@dataclass
class Course:
    id: str
    name: str
    teacher: str = ""
    location: str = ""
    day: int = 1
    start: int = 1
    end: int = 2
    weeks: WeekSpec = field(default_factory=WeekSpec)
    color: int = 1
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "teacher": self.teacher,
            "location": self.location, "day": self.day, "start": self.start,
            "end": self.end, "weeks": self.weeks.to_dict(), "color": self.color,
            "note": self.note,
        }

    def period_text(self) -> str:
        if self.start == self.end:
            return f"第 {self.start} 节"
        return f"第 {self.start}–{self.end} 节"

    def time_text(self, periods: list[Period]) -> str:
        try:
            p1 = periods[self.start - 1]
            p2 = periods[self.end - 1]
            return f"{p1.start}–{p2.end}"
        except IndexError:
            return ""


@dataclass
class CustomField:
    label: str = ""
    value: str = ""

    def to_dict(self) -> dict:
        return {"label": self.label, "value": self.value}


@dataclass
class Exam:
    id: str
    name: str
    type: str = "闭卷"
    credits: float = 0.0
    date: str = ""
    start_time: str = "09:00"
    duration: int = 120
    location: str = ""
    seat: str = ""
    progress: int = 0
    note: str = ""
    custom: list[CustomField] = field(default_factory=list)
    color: int = 1

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "type": self.type,
            "credits": self.credits, "date": self.date,
            "start_time": self.start_time, "duration": self.duration,
            "location": self.location, "seat": self.seat,
            "progress": self.progress, "note": self.note,
            "custom": [f.to_dict() for f in self.custom], "color": self.color,
        }

    def date_obj(self) -> date | None:
        try:
            return date.fromisoformat(self.date)
        except (ValueError, TypeError):
            return None

    def start_dt(self) -> datetime | None:
        d = self.date_obj()
        if d is None or not valid_time(self.start_time):
            return None
        return datetime.combine(d, time.fromisoformat(self.start_time))

    def end_dt(self) -> datetime | None:
        start = self.start_dt()
        if start is None:
            return None
        return start + timedelta(minutes=int(self.duration or 0))

    def end_time(self) -> str:
        start = self.start_dt()
        end = self.end_dt()
        if not start or not end:
            return ""
        return end.strftime("%H:%M")

    def time_range(self) -> str:
        return f"{self.start_time}–{self.end_time()}"


@dataclass
class Task:
    id: str
    text: str
    type: str = "once"
    done: bool = False
    created: str = field(default_factory=lambda: date.today().isoformat())
    done_date: str | None = None
    deadline: str | None = None
    history: dict[str, str] = field(default_factory=dict)
    note: str = ""

    @property
    def is_cycle(self) -> bool:
        return self.type in ("daily", "weekly")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "type": self.type,
            "done": self.done,
            "created": self.created,
            "done_date": self.done_date,
            "deadline": self.deadline,
            "history": dict(self.history),
            "note": self.note,
        }


@dataclass
class Settings:
    term_name: str = ""
    term_start: date = field(default_factory=lambda: monday_of(date.today()))
    total_weeks: int = 18
    show_weekend: bool = True
    glass: int = 70
    reduce_motion: bool = False
    onboarded: bool = False
    checklist_dismissed: bool = False
    theme_mode: str = "light"
    hints_dismissed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "term_name": self.term_name,
            "term_start": self.term_start.isoformat(),
            "total_weeks": self.total_weeks,
            "show_weekend": self.show_weekend,
            "glass": self.glass,
            "reduce_motion": self.reduce_motion,
            "onboarded": self.onboarded,
            "checklist_dismissed": self.checklist_dismissed,
            "theme_mode": self.theme_mode,
            "hints_dismissed": list(self.hints_dismissed),
        }


@dataclass
class AppData:
    version: int = DATA_VERSION
    sample: bool = False
    settings: Settings = field(default_factory=Settings)
    periods: list[Period] = field(default_factory=list)
    courses: list[Course] = field(default_factory=list)
    exams: list[Exam] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    exam_types: list[str] = field(default_factory=lambda: list(DEFAULT_EXAM_TYPES))

    # ---------- 序列化 ----------
    def to_dict(self) -> dict:
        return {
            "version": DATA_VERSION,
            "sample": self.sample,
            "settings": self.settings.to_dict(),
            "periods": [p.to_dict() for p in self.periods],
            "courses": [c.to_dict() for c in self.courses],
            "exams": [e.to_dict() for e in self.exams],
            "tasks": [t.to_dict() for t in self.tasks],
            "exam_types": list(self.exam_types),
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "AppData":
        if not isinstance(raw, dict):
            raise ValueError("数据格式不正确")
        data = cls()
        settings = raw.get("settings")
        if isinstance(settings, dict):
            data.settings = _settings_from_dict(settings)

        data.periods = _periods_from_list(raw.get("periods"))
        n_periods = len(data.periods)
        total = data.settings.total_weeks

        courses = []
        for item in raw.get("courses") or []:
            if isinstance(item, dict):
                course = _course_from_dict(item, n_periods, total)
                if course is not None:
                    courses.append(course)
        data.courses = courses

        exams = []
        for item in raw.get("exams") or []:
            if isinstance(item, dict):
                exam = _exam_from_dict(item)
                if exam is not None:
                    exams.append(exam)
        data.exams = exams

        tasks = []
        for item in raw.get("tasks") or []:
            task = _task_from_dict(item)
            if task is not None:
                tasks.append(task)
        data.tasks = tasks

        types = []
        for t in raw.get("exam_types") or []:
            t = str(t).strip()
            if t and t not in types:
                types.append(t)
        for e in data.exams:
            if e.type and e.type not in types:
                types.append(e.type)
        data.exam_types = types or list(DEFAULT_EXAM_TYPES)
        data.sample = bool(raw.get("sample"))
        return data


def _settings_from_dict(raw: dict) -> Settings:
    s = Settings()
    s.term_name = str(raw.get("term_name") or "").strip()[:40] or default_term_name()
    try:
        s.term_start = date.fromisoformat(str(raw.get("term_start") or ""))
    except (ValueError, TypeError):
        s.term_start = monday_of(date.today())
    try:
        s.total_weeks = clamp(int(raw.get("total_weeks") or 18), 1, 30)
    except (TypeError, ValueError):
        s.total_weeks = 18
    s.show_weekend = bool(raw.get("show_weekend", True))
    try:
        s.glass = clamp(int(raw.get("glass", 70)), 0, 100)
    except (TypeError, ValueError):
        s.glass = 70
    s.reduce_motion = bool(raw.get("reduce_motion", False))
    s.onboarded = bool(raw.get("onboarded", False))
    s.checklist_dismissed = bool(raw.get("checklist_dismissed", False))
    mode = str(raw.get("theme_mode") or "light").strip().lower()
    s.theme_mode = "dark" if mode == "dark" else "light"
    dismissed = []
    for page in raw.get("hints_dismissed") or []:
        name = str(page or "").strip()
        if name and name not in dismissed:
            dismissed.append(name[:20])
    s.hints_dismissed = dismissed
    return s


def _periods_from_list(raw) -> list[Period]:
    periods: list[Period] = []
    if isinstance(raw, list):
        for item in raw[:16]:
            if not isinstance(item, dict):
                continue
            start = norm_hhmm(item.get("start"), "08:00")
            end = norm_hhmm(item.get("end"), minutes_to_time(time_to_minutes(start) + 45))
            if time_to_minutes(end) <= time_to_minutes(start):
                end = minutes_to_time(time_to_minutes(start) + 45)
            periods.append(Period(start, end))
    if len(periods) < 2:
        periods = [Period(a, b) for a, b in DEFAULT_PERIODS]
    return periods


def _course_from_dict(raw: dict, n_periods: int, total_weeks: int) -> Course | None:
    name = str(raw.get("name") or "").strip()[:60]
    if not name:
        return None
    try:
        day = clamp(int(raw.get("day") or 1), 1, 7)
        start = clamp(int(raw.get("start") or 1), 1, n_periods)
        end = clamp(int(raw.get("end") or start), start, n_periods)
    except (TypeError, ValueError):
        day, start, end = 1, 1, 2
    weeks = WeekSpec.from_dict(raw.get("weeks"))
    if weeks.mode == "custom" and not parse_weeks_text(weeks.text, total_weeks):
        weeks.mode = "all"
        weeks.text = ""
    try:
        color = clamp(int(raw.get("color") or 1), 1, 8)
    except (TypeError, ValueError):
        color = 1
    return Course(
        id=str(raw.get("id") or new_id("c")),
        name=name,
        teacher=str(raw.get("teacher") or "").strip()[:40],
        location=str(raw.get("location") or "").strip()[:40],
        day=day, start=start, end=end, weeks=weeks, color=color,
        note=str(raw.get("note") or "").strip()[:300],
    )


def _exam_from_dict(raw: dict) -> Exam | None:
    name = str(raw.get("name") or "").strip()[:60]
    if not name:
        return None
    try:
        d = date.fromisoformat(str(raw.get("date") or ""))
        date_text = d.isoformat()
    except (ValueError, TypeError):
        return None
    start_time = norm_hhmm(raw.get("start_time"), "09:00")
    try:
        duration = clamp(int(raw.get("duration") or 120), 5, 600)
    except (TypeError, ValueError):
        duration = 120
    try:
        credits = clamp(float(raw.get("credits") or 0), 0, 30)
    except (TypeError, ValueError):
        credits = 0.0
    try:
        progress = clamp(int(raw.get("progress") or 0), 0, 100)
    except (TypeError, ValueError):
        progress = 0
    custom = []
    for f in raw.get("custom") or []:
        if not isinstance(f, dict):
            continue
        label = str(f.get("label") or "").strip()[:20]
        value = str(f.get("value") or "").strip()[:80]
        if label or value:
            custom.append(CustomField(label, value))
    try:
        color = clamp(int(raw.get("color") or 1), 1, 8)
    except (TypeError, ValueError):
        color = 1
    return Exam(
        id=str(raw.get("id") or new_id("e")),
        name=name,
        type=str(raw.get("type") or "闭卷").strip()[:20] or "闭卷",
        credits=credits, date=date_text, start_time=start_time,
        duration=duration,
        location=str(raw.get("location") or "").strip()[:40],
        seat=str(raw.get("seat") or "").strip()[:20],
        progress=progress,
        note=str(raw.get("note") or "").strip()[:500],
        custom=custom, color=color,
    )



def _parse_iso_date(text) -> str | None:
    try:
        return date.fromisoformat(str(text or "")).isoformat()
    except (ValueError, TypeError):
        return None


def _task_from_dict(raw: dict) -> Task | None:
    if not isinstance(raw, dict):
        return None
    text = str(raw.get("text") or "").strip()[:120]
    if not text:
        return None
    ttype = str(raw.get("type") or "once").strip().lower()
    if ttype not in TASK_TYPES:
        ttype = "once"
    history = {}
    for key, value in (raw.get("history") or {}).items():
        k = _parse_iso_date(key)
        if k:
            history[k] = str(value or "")[:32]
    deadline = _parse_iso_date(raw.get("deadline"))
    done_date = _parse_iso_date(raw.get("done_date"))
    return Task(
        id=str(raw.get("id") or new_id("t")),
        text=text,
        type=ttype,
        done=bool(raw.get("done")),
        created=_parse_iso_date(raw.get("created")) or date.today().isoformat(),
        done_date=done_date,
        deadline=deadline,
        history=history,
        note=str(raw.get("note") or "").strip()[:300],
    )


def same_week(d1: str, d2: str) -> bool:
    try:
        a = date.fromisoformat(d1).isocalendar()
        b = date.fromisoformat(d2).isocalendar()
        return (a[0], a[1]) == (b[0], b[1])
    except (ValueError, TypeError):
        return False


def rollover_tasks(tasks: list[Task], today: date | None = None) -> bool:
    """跨天/跨周重置循环待办；已完成的单次待办在次日移除。"""
    current = (today or date.today()).isoformat()
    changed = False
    kept: list[Task] = []
    for t in tasks:
        if t.type == "daily":
            if t.done and t.done_date and t.done_date < current:
                t.done = False
                t.done_date = None
                changed = True
            kept.append(t)
        elif t.type == "weekly":
            if t.done and t.done_date and not same_week(t.done_date, current):
                t.done = False
                t.done_date = None
                changed = True
            kept.append(t)
        else:
            if t.done and t.done_date and t.done_date < current:
                changed = True
                continue
            kept.append(t)
    if changed:
        tasks[:] = kept
    return changed


def task_sort_key(task: Task):
    if task.type == "daily":
        return (0, 0, "", task.created, task.id)
    if task.type == "weekly":
        return (0, 1, "", task.created, task.id)
    return (1, 2, task.deadline or "9999-12-31", task.created, task.id)


def sorted_tasks(tasks: list[Task]) -> list[Task]:
    return sorted(tasks, key=task_sort_key)


def task_stats(tasks: list[Task]) -> tuple[int, int, int]:
    total = len(tasks)
    done = sum(1 for t in tasks if t.done)
    return total, done, total - done


def task_due_state(task: Task, today: date | None = None) -> str | None:
    if task.type != "once" or not task.deadline:
        return None
    current = today or date.today()
    try:
        due = date.fromisoformat(task.deadline)
    except (ValueError, TypeError):
        return None
    delta = (due - current).days
    if delta < 0:
        return "overdue"
    if delta == 0:
        return "today"
    if delta <= 3:
        return "soon"
    return "future"


# --------------------------------------------------------------------------
# 课程与考试计算
# --------------------------------------------------------------------------
def course_in_week(course: Course, week: int, total_weeks: int) -> bool:
    return int(week) in expand_weeks(course.weeks, total_weeks)


def course_conflicts(courses: list[Course], course: Course, total_weeks: int):
    """返回 [(另一门课, 重叠周次列表), ...]。"""
    mine = expand_weeks(course.weeks, total_weeks)
    result = []
    for other in courses:
        if other.id == course.id or other.day != course.day:
            continue
        if other.start > course.end or other.end < course.start:
            continue
        both = mine & expand_weeks(other.weeks, total_weeks)
        if both:
            result.append((other, sorted(both)))
    return result


def conflicts_map(courses: list[Course], total_weeks: int) -> dict[str, list[tuple[Course, list[int]]]]:
    return {c.id: course_conflicts(courses, c, total_weeks) for c in courses}


def exam_status(exam: Exam, now: datetime | None = None) -> str:
    start = exam.start_dt()
    end = exam.end_dt()
    if start is None or end is None:
        return "wait"
    current = now or datetime.now()
    if current >= end:
        return "done"
    if current >= start:
        return "live"
    return "wait"


def upcoming_exams(exams: list[Exam], now: datetime | None = None) -> list[Exam]:
    current = now or datetime.now()
    result = [e for e in exams if exam_status(e, current) != "done"]
    result.sort(key=lambda e: e.start_dt() or datetime.max)
    return result


def exam_conflicts(exams: list[Exam], exam: Exam) -> list[Exam]:
    start, end = exam.start_dt(), exam.end_dt()
    if not start or not end:
        return []
    result = []
    for other in exams:
        if other.id == exam.id:
            continue
        os_, oe = other.start_dt(), other.end_dt()
        if not os_ or not oe:
            continue
        if start < oe and os_ < end:
            result.append(other)
    return result


def exam_class_conflicts(exam: Exam, data: AppData) -> list[Course]:
    """考试时间是否落在当天课程的上课时间内。"""
    d = exam.date_obj()
    if d is None:
        return []
    start, end = exam.start_dt(), exam.end_dt()
    if not start or not end:
        return []
    week = (d - data.settings.term_start).days // 7 + 1
    if week < 1 or week > data.settings.total_weeks:
        return []
    day = d.isoweekday()
    result = []
    for c in data.courses:
        if c.day != day or not course_in_week(c, week, data.settings.total_weeks):
            continue
        if c.start - 1 >= len(data.periods) or c.end - 1 >= len(data.periods):
            continue
        p1, p2 = data.periods[c.start - 1], data.periods[c.end - 1]
        cs, ce = time_to_minutes(p1.start), time_to_minutes(p2.end)
        if ranges_overlap(start.hour * 60 + start.minute, end.hour * 60 + end.minute, cs, ce):
            result.append(c)
    return result


def days_until(target: date, today: date | None = None) -> int:
    return (target - (today or date.today())).days


def relative_day_text(target: date, today: date | None = None) -> str:
    n = days_until(target, today)
    if n == 0:
        return "今天"
    if n == 1:
        return "明天"
    if n == -1:
        return "昨天"
    if n > 1:
        return f"还有 {n} 天"
    return f"{abs(n)} 天前"


# --------------------------------------------------------------------------
# 示例数据
# --------------------------------------------------------------------------
# 全新安装时的默认学期：2026-2027 学年第一学期，开学第一周周一 2026-09-14。
# 设置页里随时可以改成自己的学期。
DEFAULT_TERM_NAME = "2026-2027学年第1学期"
DEFAULT_TERM_START = date(2026, 9, 14)


def blank_data() -> AppData:
    """全新的空白数据：没有课程、考试与待办，只保留默认学期与作息。"""
    data = AppData()
    data.settings = Settings(
        term_name=DEFAULT_TERM_NAME,
        term_start=DEFAULT_TERM_START,
        total_weeks=18,
    )
    data.periods = default_periods()
    return data


def sample_data() -> AppData:
    today = date.today()
    term_start = monday_of(today) - timedelta(weeks=8)
    data = AppData()
    data.sample = True
    data.settings = Settings(
        term_name=default_term_name(today), term_start=term_start,
        total_weeks=18, show_weekend=True, glass=70,
    )
    data.periods = [Period(a, b) for a, b in DEFAULT_PERIODS]
    data.courses = [
        Course(new_id("c"), "高等数学 A（下）", "张伟", "教二-201", 1, 1, 2, WeekSpec(), 1),
        Course(new_id("c"), "大学物理（二）", "李娜", "教二-105", 1, 3, 4, WeekSpec(), 8),
        Course(new_id("c"), "程序设计基础", "王强", "计科楼-302", 2, 1, 2, WeekSpec(), 2),
        Course(new_id("c"), "大学英语（三）", "刘洋", "外语楼-208", 2, 5, 6, WeekSpec(), 3),
        Course(new_id("c"), "线性代数", "陈静", "教三-110", 3, 3, 4, WeekSpec(), 5),
        Course(new_id("c"), "毛泽东思想和中国特色社会主义理论体系概论", "赵敏", "文科楼-401", 4, 1, 2, WeekSpec(), 4),
        Course(new_id("c"), "体育（篮球）", "孙鹏", "东区篮球场", 4, 7, 8, WeekSpec(), 6),
        Course(new_id("c"), "数据结构", "周涛", "计科楼-401", 5, 3, 4, WeekSpec(), 7),
        Course(new_id("c"), "概率论与数理统计", "吴倩", "教三-205", 5, 1, 2, WeekSpec("even", ""), 2),
        Course(new_id("c"), "电路实验", "郑凯", "实验楼-B207", 6, 3, 4, WeekSpec("custom", "3-14"), 4),
    ]
    offsets = [16, 20, 24, 27, 31]
    times = ["09:00", "14:00", "09:00", "14:30", "09:00"]
    durations = [120, 120, 120, 90, 120]
    rooms = ["教三-201", "教二-108", "教三-305", "计科楼-302", "教二-201"]
    seats = ["A-12", "B-07", "", "C-21", ""]
    credits = [5, 4, 3, 4, 4]
    progress = [60, 40, 25, 55, 10]
    types = ["闭卷", "闭卷", "机考", "开卷", "闭卷"]
    for i, course in enumerate(data.courses[:5]):
        data.exams.append(Exam(
            new_id("e"), course.name, types[i], credits[i],
            (today + timedelta(days=offsets[i])).isoformat(), times[i],
            durations[i], rooms[i], seats[i], progress[i],
            "", [], (i % 8) + 1,
        ))
    data.exams[0].custom = [CustomField("允许文具", "黑色签字笔、直尺")]
    data.exams[0].note = "提前 20 分钟入场，带学生证。"
    data.exams[2].custom = [CustomField("考试系统", "PTA / 机房 C 区")]

    today_text = today.isoformat()
    done_stamp = f"{today_text}T08:30:00"
    data.tasks = [
        Task(new_id("t"), "背 30 个六级单词", "daily"),
        Task(new_id("t"), "整理高数错题", "daily", True, today_text, today_text,
             None, {today_text: done_stamp}),
        Task(new_id("t"), "每周课程复盘", "weekly"),
        Task(new_id("t"), "提交大学物理实验报告", "once", False, today_text, None,
             (today + timedelta(days=3)).isoformat()),
        Task(new_id("t"), "预约图书馆研讨间", "once", False, today_text, None,
             (today - timedelta(days=1)).isoformat()),
    ]
    return data


# --------------------------------------------------------------------------
# 持久化
# --------------------------------------------------------------------------
def data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / STORE_DIR_NAME


def data_path() -> Path:
    return data_dir() / STORE_FILE_NAME


def save_data(data: AppData, path: Path | str | None = None) -> Path:
    target = Path(path) if path else data_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(data.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, target)
    return target


def load_data(path: Path | str | None = None) -> AppData:
    target = Path(path) if path else data_path()
    if not target.exists():
        return blank_data()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        return AppData.from_dict(raw)
    except Exception:
        try:
            target.replace(target.with_suffix(target.suffix + ".bad"))
        except OSError:
            pass
        return blank_data()


def export_data(data: AppData, path: Path | str) -> Path:
    return save_data(data, path)


def import_data(path: Path | str) -> AppData:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "courses" not in raw and "settings" not in raw:
        raise ValueError("这个文件看起来不是课表备份")
    return AppData.from_dict(raw)


# --------------------------------------------------------------------------
# 日历导出
# --------------------------------------------------------------------------
def _ics_escape(text: str) -> str:
    return (str(text or "")
            .replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\r\n", "\\n")
            .replace("\n", "\\n"))


def _ics_fold(line: str) -> list[str]:
    """按 RFC 5545 折行：每行（含续行前导空格）不超过 75 个 UTF-8 字节。"""
    if len(line.encode("utf-8")) <= 75:
        return [line]
    parts: list[str] = []
    buf = ""
    for ch in line:
        prefix = " " if parts else ""
        if len((prefix + buf + ch).encode("utf-8")) > 75:
            parts.append(prefix + buf)
            buf = ch
        else:
            buf += ch
    if buf or not parts:
        parts.append((" " if parts else "") + buf)
    return parts


def _ics_dt(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def build_ics(data: AppData, now: datetime | None = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//CampusPlanner//CN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "X-WR-CALNAME:" + _ics_escape(data.settings.term_name),
        "X-WR-TIMEZONE:Asia/Shanghai",
    ]
    total = data.settings.total_weeks
    for course in data.courses:
        for week in sorted(expand_weeks(course.weeks, total)):
            day = date_of_week_day(data.settings.term_start, week, course.day)
            try:
                p1 = data.periods[course.start - 1]
                p2 = data.periods[course.end - 1]
            except IndexError:
                continue
            start = datetime.combine(day, time.fromisoformat(p1.start))
            end = datetime.combine(day, time.fromisoformat(p2.end))
            lines += [
                "BEGIN:VEVENT",
                f"UID:{course.id}-w{week}@campusplanner",
                f"DTSTAMP:{stamp}",
                f"DTSTART:{_ics_dt(start)}",
                f"DTEND:{_ics_dt(end)}",
                "SUMMARY:" + _ics_escape(course.name),
                "LOCATION:" + _ics_escape(course.location),
                "DESCRIPTION:" + _ics_escape(
                    f"{course.teacher} · 第 {week} 周 · {weeks_label(course.weeks, total)}"
                    + (f"\n{course.note}" if course.note else "")),
                "END:VEVENT",
            ]
    for exam in data.exams:
        start = exam.start_dt()
        end = exam.end_dt()
        if not start or not end:
            continue
        desc_parts = [exam.type or "考试"]
        if exam.credits:
            desc_parts.append(f"{exam.credits:g} 学分")
        if exam.seat:
            desc_parts.append(f"座位 {exam.seat}")
        if exam.note:
            desc_parts.append(exam.note)
        lines += [
            "BEGIN:VEVENT",
            f"UID:{exam.id}@campusplanner",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{_ics_dt(start)}",
            f"DTEND:{_ics_dt(end)}",
            "SUMMARY:" + _ics_escape("[考试] " + exam.name),
            "LOCATION:" + _ics_escape(exam.location),
            "DESCRIPTION:" + _ics_escape(" · ".join(desc_parts)),
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    folded: list[str] = []
    for line in lines:
        folded.extend(_ics_fold(line))
    return "\r\n".join(folded) + "\r\n"


def export_ics(data: AppData, path: Path | str) -> Path:
    target = Path(path)
    target.write_text(build_ics(data), encoding="utf-8", newline="")
    return target


# --------------------------------------------------------------------------
# 作息表辅助
# --------------------------------------------------------------------------
def redistribute_periods(periods: list[Period], duration: int = 45, gap: int = 10) -> list[Period]:
    """按固定时长与课间重新排布所有节次，从第一节开始时间起算。"""
    if not periods:
        return []
    start = time_to_minutes(periods[0].start)
    step = max(5, int(duration)) + max(0, int(gap))
    result = []
    for i in range(len(periods)):
        s = start + i * step
        result.append(Period(minutes_to_time(s), minutes_to_time(s + max(5, int(duration)))))
    return result


def period_duration(period: Period) -> int:
    return time_to_minutes(period.end) - time_to_minutes(period.start)
