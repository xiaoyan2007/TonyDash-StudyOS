"""粘贴文本解析 —— 准确率最高的导入路径。

截图 OCR 是在猜像素，最好也就七八成；而**复制出来的文本是系统给的**，
所以这条路必须做到几乎不丢信息。支持三种真实来源：

1. **URP/金智「全部课程清单」**：一行一门课，字段用制表符或空格分隔，
   地点是 ``校区>>楼>>房间`` 三元组；
2. **教务网页表格**：表头是星期，行首是节次，直接按列切格（复用单格解析器）；
3. **自由文本**：一行一门课，字段顺序随意，靠正则抽星期/节次/周次，
   再从剩余片段里判地点、教师、课名。
"""

from __future__ import annotations

import re

from . import cell_parser, fields, weeks as weeks_mod
from .models import DraftCourse, ImportResult

#: 一条「课程记录」的开头：6 位以上课程号，或明确带星期+节次
_RE_HEAD_CODE = re.compile(r"^\s*(\d{6,})[\t ]")
#: 地点三元组 ``校区>>楼>>房间``。**三段都不许含空白**：写成 ``[^\t<>》]*?`` 时，
#: 在把制表符压平成一空格之后（安卓剪贴板常把 \t 变成空格），惰性量词会从头一路
#: 吃到 ``>>``，把整行都当成地点替换掉，课名/教师全丢（实测 URP 样例十门课全空名）。
_RE_TRIPLE = re.compile(r"([^\t<>》\s]*?)\s*>>\s*([^\t<>》\s]*?)\s*>>\s*([^\t<>》\s]*)")

_SEP_TAB = "\t"
_SEP_MULTI = re.compile(r"\s{2,}")


def _split_cells(line: str) -> list[str]:
    """把一行切成单元格：优先制表符，其次连续空格。"""
    if _SEP_TAB in line:
        return [c.strip() for c in line.split(_SEP_TAB)]
    if _SEP_MULTI.search(line):
        return [c.strip() for c in _SEP_MULTI.split(line.strip())]
    return [line.strip()]


def _looks_like_record_head(line: str) -> bool:
    if _RE_HEAD_CODE.match(line):
        return True
    if ">>" in line and (fields.extract_weekday(line) or fields.extract_periods(line)):
        return True
    return bool(fields.extract_weekday(line) and
                (fields.extract_periods(line) or fields.extract_weeks_text(line)))


def segment_records(lines: list[str]) -> list[str]:
    """把多行文本切成「一条课程一段」。"""
    blocks: list[list[str]] = []
    for line in lines:
        value = line.rstrip()
        if not value.strip():
            continue
        if _looks_like_record_head(value) or not blocks:
            blocks.append([value])
        else:
            blocks[-1].append(value)
    return ["\n".join(b) for b in blocks]


def _is_matrix(lines: list[str]) -> tuple[int, list[int]] | None:
    """判断是否是「表头为星期」的表格；返回 ``(表头行号, 各列对应的星期)``。"""
    for index, line in enumerate(lines[:8]):
        cells = _split_cells(line)
        days = [fields.extract_weekday(c) for c in cells]
        hit = sum(1 for d in days if d)
        # 至少两个星期列，且表头里非星期的列不超过两个（通常只有「节次」）
        if hit >= 2 and len(cells) <= hit + 2:
            return index, [d or 0 for d in days]
    return None


def parse_matrix(lines: list[str], header_index: int, days: list[int],
                 *, source: str, total: int = 0) -> ImportResult:
    """解析「星期表头 + 节次行首」的表格文本。"""
    result = ImportResult(source=source)
    for line in lines[header_index + 1:]:
        if not line.strip():
            continue
        cells = _split_cells(line)
        if len(cells) < 2:
            continue
        label = cells[0]
        periods = fields.extract_periods(label)
        if periods is None and re.fullmatch(r"\d{1,2}", label.strip()):
            periods = (int(label.strip()), int(label.strip()))
        if periods is None:
            continue
        low, high = periods
        for offset, day in enumerate(days):
            if not day:
                continue
            position = offset
            if len(cells) != len(days):
                # 列数对不上就按「第 n 个非空列」近似对齐
                position = offset
            if position >= len(cells):
                continue
            text = cells[position]
            if fields.is_noise(text):
                continue
            course = cell_parser.parse_cell(
                text, day=day, start=low, end=high, source=source, raw=text,
            )
            if course is not None:
                result.courses.append(course)
        result.periods.extend(cell_parser.time_slot_dicts(label, low))
    result.finalize()
    return result


def _parse_urp_record(text: str, *, source: str) -> DraftCourse | None:
    """解析 URP/金智那一行（可能带续行）。"""
    # 地点三元组必须在**未压平空白**的原文上提取：
    # 压平后 ``B203\t王五`` 会变成 ``B203 王五``，第三段就会把教师吞进地点。
    place = ""
    triples = _RE_TRIPLE.findall(text)
    for first, second, third in triples:
        chunk = [p.strip() for p in (first, second, third) if p and p.strip()]
        if not chunk:
            continue
        joined = _join_place(chunk)
        if joined:
            place = joined

    flat = " ".join(text.split())
    code = ""
    match = _RE_HEAD_CODE.match(flat)
    if match:
        code = match.group(1)
        flat = flat.replace(code, " ", 1)

    day = fields.extract_weekday(flat)
    periods = fields.extract_periods(flat)
    weeks_text = fields.extract_weeks_text(flat)
    parity = fields.extract_parity(flat)

    flat = _RE_TRIPLE.sub(" ", flat)

    rest = flat
    rest = re.sub(r"^\s*\d{6,}\s*", " ", rest)
    rest = fields.RE_PERIOD_RANGE.sub(" ", rest)
    rest = fields.RE_PERIOD_SINGLE.sub(" ", rest)
    rest = fields.RE_WEEKS_SUFFIX.sub(" ", rest)
    rest = fields.RE_WEEK_SINGLE.sub(" ", rest)
    rest = fields.RE_PARITY_TAG.sub(" ", rest)
    rest = fields.RE_WEEKDAY.sub(" ", rest)
    rest = fields.RE_WEEKDAY_EN.sub(" ", rest)
    rest = re.sub(r"\s+", " ", rest).strip(" \t,，、;；|/-—–")

    fragments = [f for f in re.split(r"[\t ]+", rest) if f.strip()]
    keep: list[str] = []
    teacher = ""
    for fragment in fragments:
        if fields.is_noise(fragment):
            continue
        if fields.looks_like_place(fragment) and not place:
            place = fragment
            continue
        if fields.looks_like_teacher(fragment) and keep:
            if not teacher:
                teacher = fragment
                continue
        keep.append(fragment)

    name = "".join(keep).strip()
    if not name and not place:
        return None
    note = f"课程代码 {code}" if code else ""
    course = DraftCourse(
        name=name, teacher=teacher, location=place,
        day=int(day or 1),
        start=int(periods[0]) if periods else 1,
        end=int(periods[1]) if periods else (int(periods[0]) if periods else 1),
        mode="custom" if (weeks_text or parity) else "all",
        weeks_text=weeks_text, parity=parity, note=note, source=source, raw=flat,
    )
    return course


def _join_place(parts: list[str]) -> str:
    """把 ``["主校区", "教学楼", "A202"]`` 拼成人类可读的地点。"""
    cleaned = [p for p in (x.strip() for x in parts) if p]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    # 校区信息冗余，缩到「楼 + 房间」够用；只有两段时全部保留
    if len(cleaned) >= 3 and len(cleaned[-1]) <= 12:
        return cleaned[-2] + cleaned[-1]
    return "".join(cleaned)


def _parse_generic_line(line: str, *, source: str) -> DraftCourse | None:
    """一行一门课的通用解析。"""
    flat = " ".join(line.split())
    if not flat:
        return None
    # 三元组同样要在压平之前提取（否则第三段会吞掉后面的教师）
    place = ""
    for first, second, third in _RE_TRIPLE.findall(line):
        chunk = [p.strip() for p in (first, second, third) if p and p.strip()]
        if chunk:
            place = _join_place(chunk) or place

    day = fields.extract_weekday(flat)
    periods = fields.extract_periods(flat)
    weeks_text = fields.extract_weeks_text(flat)
    parity = fields.extract_parity(flat)
    if day is None and periods is None:
        return None

    flat = _RE_TRIPLE.sub(" ", flat)

    rest = fields.strip_fields(flat)
    rest = re.sub(r"^\s*\d{6,}\s*", " ", rest)
    fragments = [f for f in re.split(r"[\t ]+", rest) if f.strip()]

    name_parts: list[str] = []
    teacher = ""
    for fragment in fragments:
        if fields.is_noise(fragment):
            continue
        if fields.looks_like_place(fragment) and not place:
            place = fragment
            continue
        if fields.looks_like_teacher(fragment) and name_parts and not teacher:
            teacher = fragment
            continue
        name_parts.append(fragment)

    name = "".join(name_parts).strip()
    if not name and not place:
        return None
    return DraftCourse(
        name=name, teacher=teacher, location=place,
        day=int(day or 1),
        start=int(periods[0]) if periods else 1,
        end=int(periods[1]) if periods else (int(periods[0]) if periods else 1),
        mode="custom" if (weeks_text or parity) else "all",
        weeks_text=weeks_text, parity=parity, source=source, raw=flat,
    )


def parse_text(text: str, *, source: str = "paste", forced: str = "") -> ImportResult:
    """解析整段粘贴文本。

    ``forced`` 可指定 ``"matrix"`` / ``"urp"`` / ``"generic"`` 跳过自动判断。
    """
    raw_lines = [line for line in str(text or "").splitlines() if line.strip()]
    result = ImportResult(source=source, meta={"lines": len(raw_lines)})
    if not raw_lines:
        result.warnings.append("没有可解析的内容。")
        return result

    mode = forced
    if not mode:
        if _is_matrix(raw_lines):
            mode = "matrix"
        elif any(">>" in line or _RE_HEAD_CODE.match(line) for line in raw_lines):
            mode = "urp"
        else:
            mode = "generic"

    if mode == "matrix":
        found = _is_matrix(raw_lines)
        if found:
            header_index, days = found
            result = parse_matrix(raw_lines, header_index, days, source=source)
            result.meta["mode"] = "matrix"
            return result
        result.warnings.append("看起来是表格，但没找到星期表头，已改用逐行解析。")
        mode = "generic"

    if mode == "urp":
        for block in segment_records(raw_lines):
            course = _parse_urp_record(block, source=source)
            if course is not None:
                result.courses.append(course)
        result.meta["mode"] = "urp"
    else:
        for line in raw_lines:
            for piece in _split_multi_course(line):
                course = _parse_generic_line(piece, source=source)
                if course is not None:
                    result.courses.append(course)
        result.meta["mode"] = "generic"

    if not result.courses:
        result.warnings.append(
            "没解析出课程。可以试试在文本里保留「周X」「第X节」「X周」这些关键字。"
        )
    result.finalize()
    return result


def _split_multi_course(line: str) -> list[str]:
    """一行里塞了两门课（用「；」或「|」分隔）时拆开。"""
    if not re.search(r"[;；|]", line):
        return [line]
    pieces = [p for p in re.split(r"[;；|]", line) if p.strip()]
    informative = [p for p in pieces if fields.extract_weekday(p) or fields.extract_periods(p)]
    return informative if len(informative) > 1 else [line]
