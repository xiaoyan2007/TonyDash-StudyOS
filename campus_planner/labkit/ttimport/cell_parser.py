"""单个单元格文本 → 课程草稿。

这是整条导入链路上最核心的解析器：OCR 逐格识别、粘贴文本的表格行、
以及 CSV/Excel 里的「一格一门课」，最终都汇到这里。

分支优先级直接沿用对 `cell_parser.dart` 的研读结论，并修掉它踩过的坑：
地点必须先判（坑①）、教师规则必须有课名（坑②）、纯数字编号不是地点（坑③）、
周次必须带「周」字（坑④）、续行明写节次要能修正范围（坑⑥）。
"""

from __future__ import annotations

import re

from . import fields
from .models import DraftCourse

#: 课程编号尾部（`高等数学A(1)_04`、`大学英语-12`）。
#: 必须带分隔符，否则 `A202` 会被吃掉尾部数字变成课名「…A」（踩坑③的变体）
_RE_CODE_TAIL = re.compile(r"(?:[_\-]|\s)\s*\d{1,4}\s*$")
#: 班级/教学班标注
_RE_CLASS_TAG = re.compile(r"[（(]\s*[^）)]{0,12}(班|教学班|合班)\s*[）)]")
#: 时间标签：第(08:00-08:45) 或 08:00-08:45
_RE_TIME_SLOT = re.compile(r"(\d{1,2})[:：](\d{2})\s*[-—–~～]\s*(\d{1,2})[:：](\d{2})")

_NICKNAME = ("体育", "英语", "数学", "语文", "物理", "化学", "生物", "历史",
             "地理", "政治", "音乐", "美术", "书法", "劳动", "自习", "班会")


def split_time_slots(text: str) -> list[tuple[str, str]]:
    """从时间栏文本里抽出 ``[(开始, 结束)]``，如 ``[("08:00","08:45")]``。"""
    out: list[tuple[str, str]] = []
    for match in _RE_TIME_SLOT.finditer(fields.clean(text)):
        start = f"{int(match.group(1)):02d}:{match.group(2)}"
        end = f"{int(match.group(3)):02d}:{match.group(4)}"
        out.append((start, end))
    return out


def time_slot_dicts(text: str, first_period: int = 1) -> list[dict]:
    """把时间栏文本变成作息表条目，供 :class:`ImportResult.periods` 使用。

    ``第1-2节 (08:00-08:45)`` → ``{"period": 1, "start": "08:00", "end": "08:45"}``。

    ``first_period`` 是这一格对应的起始节次。**一格写着「第1-2节」却只给一个时间段时，
    只认第一个节次的时间**——凭空补出来的时间会让主程序的作息表出错，宁可少一条。
    """
    out: list[dict] = []
    for offset, (start, end) in enumerate(split_time_slots(text)):
        out.append({
            "period": first_period + offset,
            "start": start, "end": end,
            "startMinute": fields.to_minutes(start), "endMinute": fields.to_minutes(end),
        })
    return out


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def parse_cell(
    lines,
    *,
    day: int | None = None,
    start: int | None = None,
    end: int | None = None,
    source: str = "ocr",
    raw: str = "",
) -> DraftCourse | None:
    """把一格里的若干行文本解析成一门课。

    返回 ``None`` 表示这一格不是课程（空白、表头、噪声）。
    """
    if isinstance(lines, str):
        lines = lines.splitlines()
    parts = []
    for line in lines or []:
        value = fields.clean(line)
        if not value:
            continue
        if fields.is_noise(value) or fields.is_weekday_header(value):
            continue
        if fields.is_period_header(value):
            continue
        parts.append(value)
    if not parts:
        return None

    name_parts: list[str] = []
    room = ""
    building = ""
    teacher = ""
    weeks_parts: list[str] = []
    parity = ""
    cur_start = start
    cur_end = end
    explicit_period = False
    name_closed = False
    notes: list[str] = []

    for part in parts:
        rest = part

        # 0) 单双周标记（「1-15周(单)」里的括号信息不在周次片段内，必须单独捞）
        if not parity:
            parity = fields.extract_parity(rest)
            if parity:
                rest = fields.RE_PARITY_TAG.sub(" ", rest)

        # 1) 节次：范围优先，其次是单节（续行能修正范围 —— 修掉坑⑥）
        match = fields.RE_PERIOD_RANGE.search(rest)
        if match:
            low, high = int(match.group(1)), int(match.group(2))
            if low > high:
                low, high = high, low
            cur_start, cur_end = low, high
            explicit_period = True
            rest = rest[:match.start()] + " " + rest[match.end():]
        else:
            match = fields.RE_PERIOD_SINGLE.search(rest)
            if match:
                value = int(match.group(1))
                if cur_start is None:
                    cur_start = cur_end = value
                elif value in (cur_start - 1, cur_end + 1):
                    cur_start, cur_end = min(cur_start, value), max(cur_end, value)
                elif value < cur_start:
                    cur_start = value
                elif value > cur_end:
                    cur_end = value
                explicit_period = True
                rest = rest[:match.start()] + " " + rest[match.end():]

        # 2) 周次：必须带「周」字，可多段（修掉坑④⑤）
        week_match = fields.RE_WEEKS_SUFFIX.search(rest)
        if week_match:
            weeks_parts.append(week_match.group(1))
            rest = rest[:week_match.start()] + " " + rest[week_match.end():]
        else:
            week_match = fields.RE_WEEK_SINGLE.search(rest)
            if week_match:
                weeks_parts.append(week_match.group(1))
                rest = rest[:week_match.start()] + " " + rest[week_match.end():]

        # 3) 星期（有些文本格自带星期）
        if day is None:
            found = fields.extract_weekday(rest)
            if found:
                day = found
                rest = fields.RE_WEEKDAY.sub(" ", rest)

        rest = rest.strip(" \t,，、;；|/\\-—–")
        if not rest:
            continue

        # 一格里的文字可能是多行，也可能是一行里空格分隔（表格粘贴/CSV 常见）。
        # 多行时每行就是一个字段，空格分隔时才需要额外的小心：
        # 「大学 英语」是课名，「高等数学 A202 张三」才是三个字段。
        tokens = rest.split()
        multi = len(tokens) > 1
        if not multi:
            tokens = [rest]
        name_len = len("".join(name_parts))

        for token in tokens:
            token = token.strip(" \t,，、;；|/\\-—–")
            if not token:
                continue

            # 4) 地点优先于课名（修掉坑①）
            if fields.looks_like_place(token):
                if not room:
                    room = token
                elif not building:
                    building = token
                else:
                    notes.append(token)
                continue

            # 5) 教师：必须先有课名，否则「体育」会被当成人名（修掉坑②）
            if fields.looks_like_teacher(token) and name_parts:
                confident = (not multi) or len(tokens) >= 3 or name_len >= 3
                if confident and not teacher:
                    teacher = token
                    name_closed = True
                    continue

            if name_closed:
                notes.append(token)
                continue
            name_parts.append(token)

    name = "".join(part.strip() for part in name_parts).strip()
    name = _RE_CLASS_TAG.sub("", name)
    code = ""
    tail = _RE_CODE_TAIL.search(name)
    if tail and len(name) > 4:
        code = tail.group(0).strip("_- ")
        name = _RE_CODE_TAIL.sub("", name).strip()
    name = name.strip("_ -—–·")

    location = building + room if building and room and not room.startswith(building) else (room or building)

    if not name and not location:
        return None
    if name and len(name) < 2 and not location:
        return None
    if not name and location:
        name = ""

    weeks_text = ",".join(weeks_parts)
    note_bits = []
    if code:
        note_bits.append(f"课程代码 {code}")
    note_bits.extend(notes)
    if explicit_period and start is not None and cur_start != start:
        note_bits.append("以格内标注的节次为准")

    course = DraftCourse(
        name=name,
        teacher=teacher,
        location=location,
        day=int(day or 1),
        start=int(cur_start if cur_start is not None else 1),
        end=int(cur_end if cur_end is not None else (cur_start if cur_start is not None else 1)),
        mode="all",
        weeks_text=weeks_text,
        parity=parity,
        note="；".join(note_bits),
        source=source,
        raw=raw or " / ".join(parts),
    )
    if weeks_text or parity:
        course.mode = "custom"
    return course


def merge_adjacent(courses: list[DraftCourse]) -> list[DraftCourse]:
    """把被节次线切成上下两半的同一门课合回一条。

    仅当「课程名相同、星期相同、节次首尾相接」时才合并（修掉坑⑧：
    同名但不相邻绝不能合并，否则会合出「第 1-6 节」这种假课）。
    """
    out: list[DraftCourse] = []
    for course in courses:
        if out:
            prev = out[-1]
            same = (
                prev.name == course.name
                and prev.day == course.day
                and prev.end + 1 == course.start
                and prev.location == course.location
            )
            if same:
                prev.end = course.end
                if course.weeks_text:
                    prev.mode = "custom"
                    prev.weeks_text = ",".join(
                        _dedupe([prev.weeks_text, course.weeks_text])
                    )
                for bit in (course.teacher, course.note):
                    if bit and bit not in prev.note:
                        prev.note = "；".join(x for x in (prev.note, bit) if x)
                continue
        out.append(course)
    return out
