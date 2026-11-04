"""CSV / Excel 课表导入。

两条策略，按数据形态自动选择：

* **规整行表**：每行一门课，列名可识别（课程名/星期/节次/周次/教师/地点/教室），
  逐行映射 —— 这是教务系统导出的 Excel 的典型形态；
* **课表格子**：表头是星期、行首是节次，每个数据格就是一门课 ——
  直接交给单格解析器，和学生自己排的课表一致。

CSV 读取**优先用标准库**，不强制依赖 pandas；Excel 用 openpyxl（主程序环境已装），
两者都缺席时给出明确提示而不是崩掉。
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from . import cell_parser, fields, text_parser
from .models import DraftCourse, ImportResult

# --------------------------------------------------------------- 列名识别
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("课程名称", "课程名", "课程", "科目", "教学班名称", "名称", "课名",
             "coursename", "course", "name", "subject"),
    "teacher": ("教师", "老师", "任课教师", "授课教师", "任课老师", "上课教师",
                "teacher", "instructor"),
    "day": ("星期", "周几", "上课星期", "weekday", "day", "week"),
    "period": ("节次", "节", "上课节次", "时间", "上课时间", "period", "section",
               "time", "第几节"),
    "weeks": ("周次", "上课周次", "周数", "教学周", "weeks", "weeklist",
              "weekrange", "weekspan"),
    "location": ("地点", "上课地点", "教室", "上课教室", "场地", "position",
                 "room", "location", "classroom"),
    "note": ("备注", "说明", "note", "remark", "memo"),
}

DAY_WORDS = {1: ("一", "1", "mon", "周一", "星期一"), 2: ("二", "2", "tue"),
             3: ("三", "3", "wed"), 4: ("四", "4", "thu"),
             5: ("五", "5", "fri"), 6: ("六", "6", "sat"),
             7: ("日", "天", "7", "sun")}


def _norm_header(value: str) -> str:
    return re.sub(r"[\s_*（）()：:]", "", str(value or "")).lower()


def map_columns(header: list[str]) -> dict[str, int]:
    """把表头映射成 ``{字段: 列号}``。"""
    mapping: dict[str, int] = {}
    normalized = [_norm_header(h) for h in header]
    for field, aliases in COLUMN_ALIASES.items():
        for index, head in enumerate(normalized):
            if not head:
                continue
            if index in mapping.values():
                continue
            if head in aliases or any(head == _norm_header(a) for a in aliases):
                mapping[field] = index
                break
        else:
            for index, head in enumerate(normalized):
                if not head or index in mapping.values():
                    continue
                if any(_norm_header(a) in head for a in aliases if len(a) >= 2):
                    mapping[field] = index
                    break
    return mapping


def _parse_day(value: str) -> int | None:
    text = fields.clean(value)
    if not text:
        return None
    found = fields.extract_weekday(text)
    if found:
        return found
    for day, words in DAY_WORDS.items():
        for word in words:
            if text == word or text.lower() == word:
                return day
    match = re.search(r"[1-7]", text)
    if match:
        return int(match.group(0))
    return None


def _rows_from_csv(path: Path) -> list[list[str]]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gbk", "gb18030", "utf-16"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    return [[c.strip() for c in row] for row in reader if any(c.strip() for c in row)]


def _rows_from_excel(path: Path) -> list[list[str]]:
    try:
        import openpyxl  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "读取 Excel 需要 openpyxl：请先安装（py -3 -m pip install openpyxl）"
        ) from exc
    book = openpyxl.load_workbook(path, data_only=True, read_only=True)
    sheet = book[book.sheetnames[0]]
    rows: list[list[str]] = []
    for row in sheet.iter_rows(values_only=True):
        cells = ["" if v is None else str(v).strip() for v in row]
        if any(cells):
            rows.append(cells)
    book.close()
    return rows


def rows_from_file(path: Path) -> list[list[str]]:
    """按扩展名读取为二维字符串表。"""
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm", ".xltx"):
        return _rows_from_excel(path)
    if suffix == ".xls":
        raise RuntimeError("旧版 .xls 请先另存为 .xlsx 或 CSV。")
    if suffix in (".csv", ".txt", ".tsv"):
        return _rows_from_csv(path)
    # 未知扩展名：先当 CSV 试，失败再试 Excel
    try:
        return _rows_from_csv(path)
    except Exception:
        return _rows_from_excel(path)


def _is_grid_shape(rows: list[list[str]]) -> tuple[int, list[int]] | None:
    """识别「课表格子」形态；返回 ``(表头行号, 每列星期)``。"""
    for index, row in enumerate(rows[:8]):
        days = [fields.extract_weekday(cell) for cell in row]
        hit = sum(1 for d in days if d)
        if hit >= 2 and len(row) <= hit + 2:
            return index, [d or 0 for d in days]
    return None


def parse_rows(rows: list[list[str]], *, source: str = "excel") -> ImportResult:
    """解析二维表（Excel/CSV 共用）。"""
    result = ImportResult(source=source, meta={"rows": len(rows)})
    if not rows:
        result.warnings.append("文件里没有数据。")
        return result

    grid = _is_grid_shape(rows)
    header = [_norm_header(c) for c in rows[0]]
    mapping = map_columns(rows[0])

    if grid and not ({"name", "day"} <= set(mapping)):
        header_index, days = grid
        for row in rows[header_index + 1:]:
            label = row[0] if row else ""
            periods = fields.extract_periods(label)
            if periods is None and re.fullmatch(r"\d{1,2}", label.strip()):
                periods = (int(label.strip()), int(label.strip()))
            if periods is None:
                continue
            low, high = periods
            for offset, day in enumerate(days):
                if not day or offset >= len(row):
                    continue
                text = row[offset]
                if fields.is_noise(text):
                    continue
                course = cell_parser.parse_cell(
                    text, day=day, start=low, end=high, source=source, raw=text,
                )
                if course is not None:
                    result.courses.append(course)
        result.meta["mode"] = "grid"
        result.finalize()
        return result

    if not mapping:
        result.warnings.append(
            "认不出表头列名（需要「课程名/星期/节次/周次」之类）。"
            "如果这是课表格子，请确保表头有「星期一…星期日」。"
        )
        return result

    for row in rows[1:]:
        def cell(field: str) -> str:
            index = mapping.get(field)
            if index is None or index >= len(row):
                return ""
            return fields.clean(row[index])

        name = cell("name")
        if not name or fields.is_noise(name):
            continue
        day = _parse_day(cell("day"))
        periods = fields.extract_periods(cell("period"))
        raw_weeks = cell("weeks")
        # 「周次」列常写成 1-16 / 1-16周 / 1-15周(单)，这里同时取周次与单双周
        parity = fields.extract_parity(raw_weeks)
        weeks_text = re.sub(r"[^\d,\-]", "", fields.extract_weeks_text(raw_weeks) or raw_weeks)
        location = cell("location")
        teacher = cell("teacher")

        course = DraftCourse(
            name=name,
            teacher=teacher if fields.looks_like_teacher(teacher) else teacher,
            location=location,
            day=int(day or 1),
            start=int(periods[0]) if periods else 1,
            end=int(periods[1]) if periods else (int(periods[0]) if periods else 1),
            mode="custom" if (weeks_text or parity) else "all",
            weeks_text=weeks_text,
            parity=parity,
            note=cell("note"),
            source=source,
            raw=" | ".join(row),
        )
        if day is None:
            course.issues.append("缺少星期，已默认周一")
        result.courses.append(course)

    result.meta["mode"] = "table"
    result.meta["columns"] = sorted(mapping)
    result.finalize()
    return result


def parse_file(path: Path, *, source: str = "") -> ImportResult:
    """读取并解析 CSV/Excel 文件。"""
    path = Path(path)
    if not path.is_file():
        result = ImportResult(source=source or "file")
        result.warnings.append(f"文件不存在：{path}")
        return result
    try:
        rows = rows_from_file(path)
    except Exception as exc:
        result = ImportResult(source=source or path.suffix.lstrip("."))
        result.warnings.append(str(exc))
        return result
    result = parse_rows(rows, source=source or path.suffix.lstrip(".").lower())
    result.meta["file"] = str(path)
    return result


def parse_delimited_text(text: str, *, source: str = "csv") -> ImportResult:
    """把一段制表符/逗号分隔的文本当作表格解析（用户直接粘贴表格时用）。"""
    lines = [line for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return ImportResult(source=source)
    delimiter = "\t" if "\t" in lines[0] else ","
    rows = [[c.strip() for c in line.split(delimiter)] for line in lines]
    return parse_rows(rows, source=source)


__all__ = [
    "parse_file", "parse_rows", "parse_delimited_text", "rows_from_file",
    "map_columns", "COLUMN_ALIASES", "text_parser",
]
