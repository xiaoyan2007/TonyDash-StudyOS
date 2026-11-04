"""照片课表解析 —— 面向「列表视图」的课表截图（教务系统网页的列表版）。

与 PDF 网格版式的关键区别（都由 lab/material 的三张照片实测得出）：

* 每门课占 **2~3 个视觉行**：课名行 / 字段行（节次+周数+地点+教师+教学班…）/ 学时行
* 字段全部带标签：``周数：``、``上课地点：``、``教师：``、``考核方式：``，直接取值即可
* 星期是**左侧竖排字**（星 / 期 / 三 分三行），需要拼起来才能得到「星期三」
* 没有稳定的网格线（格线检测只能找到 3 列），所以**必须按 y 聚类成行、再按行分组**

策略：**OCR 出所有文本块（带坐标）→ 按 y 聚成视觉行 → 用「课名行 + 字段行」配对
→ 从上往下继承最近的星期 → 输出课程**。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Sequence

from .models import DraftCourse, ImportResult
from .progress import as_progress

#: 星期竖排字的候选
_WEEKDAY_CHARS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7}

#: 字段标签（列表视图里都带全角冒号）。
#: 注意 OCR 会把「周数：」认成「前周数：」「周数:」甚至「周 数：」，
#: 所以标签前面允许有多余的字，用宽松的前缀匹配。
_RE_WEEKS = re.compile(r"周\s*数\s*[:：]\s*([^\s/／]+)")
_RE_PLACE = re.compile(r"(?:上课地点|场地|地点)\s*[:：]\s*([^/／\s]+)")
_RE_TEACHER = re.compile(r"(?:教师|老师)\s*[:：]\s*([^/／\s]+)")
_RE_PERIODS = re.compile(r"^\s*(\d{1,2})\s*[-—–~～]\s*(\d{1,2})\s*$")

#: 「周数」被 OCR 认花时的兜底：`前周数`、`周數`、`周期的数`
_RE_WEEKS_FUZZY = re.compile(r"[前周課课周期]*\s*周\s*数?\s*[:：]\s*([^\s/／]+)")

#: 噪声行：工具栏、表头、学时统计行
_NOISE = (
    re.compile(r"输出\s*PDF"),
    re.compile(r"^表格$"),
    re.compile(r"列表$"),
    re.compile(r"^星期$"),
    re.compile(r"^周数\s*[:：]?\s*$"),
    re.compile(r"^(课程学时组成|周学时|总学时|学分|考核方式|教学班|选课备注|校区)"),
    re.compile(r"^(上午|下午|晚上)$"),
)


@dataclass
class _Item:
    """一个 OCR 文本块。"""

    text: str
    x: float
    y: float


def _cluster_rows(items: Sequence[_Item], tolerance: float = 25.0) -> list[list[_Item]]:
    """按 y 把块聚成视觉行（同一行的 y 差不超过 tolerance）。"""
    rows: list[list[_Item]] = []
    for item in sorted(items, key=lambda i: i.y):
        if rows and abs(item.y - rows[-1][0].y) <= tolerance:
            rows[-1].append(item)
        else:
            rows.append([item])
    for row in rows:
        row.sort(key=lambda i: i.x)
    return rows


def _is_toolbar(text: str) -> bool:
    """右上角工具栏的文本块（输出PDF / 表格 / 列表 / 残留单字）。

    实测它们贴在图片最右边，内容固定；OCR 有时把「三 列表」连成一个块，
    所以不能只按单字判断。
    """
    value = text.strip()
    if value in ("表格", "列表", "输出PDF", "输出 PDF", "田表格", "三列表", "三 列表"):
        return True
    if re.fullmatch(r"[三田兰兴]", value):
        return True
    if "输出PDF" in value or "输出 PDF" in value:
        return True
    # 「X 列表」「X 表格」这种带前导噪声字的工具栏
    if re.fullmatch(r".{0,2}(列表|表格)", value):
        return True
    return False


def _is_noise(text: str) -> bool:
    """判断一**块**文本是不是噪声（工具栏/学时统计/图例）。

    注意用「包含」而不是「整行」：学时行的块形态很杂
    （`成：理论：32，实验：32`、`兰 总学时：64`、`学分：4.0`），
    只要块里出现这些词就不该拿去当课名。
    """
    value = text.strip()
    if not value:
        return True
    if "周数" in value or "上课地点" in value or "教师" in value:
        return False
    if any(word in value for word in (
        "课程学时组成", "周学时", "总学时", "学分", "考核方式",
        "教学班", "选课备注", "校区",
    )):
        return True
    if re.match(r"^(?:成|学时)\s*[:：]", value):
        return True
    if _is_toolbar(value):
        return True
    for pattern in _NOISE:
        if pattern.fullmatch(value):
            return True
    return False


def _join(row: Sequence[_Item]) -> str:
    return " ".join(item.text.strip() for item in row)


def _find_weekday(row: Sequence[_Item], *, x_limit: float = 0.15) -> int | None:
    """在一行里认星期。

    照片里星期是**左侧竖排字**：「星」「期」「三」各自独立成块、垂直排列，
    所以不能只看「星期X」这种连写形式。判定：
    先在本行找「星期X」连写；再在**左侧区域**（x 小于图宽的 x_limit）找
    单独的「星」「期」与星期字，三个字都出现在同一行即成立。
    """
    joined = "".join(item.text.strip() for item in row)
    match = re.search(r"(?:星期|周)\s*([一二三四五六日天])", joined)
    if match:
        return _WEEKDAY_CHARS.get(match.group(1))

    left = [item.text.strip() for item in row if item.x <= x_limit]
    if "星" in left and "期" in left:
        for char in left:
            if char in _WEEKDAY_CHARS:
                return _WEEKDAY_CHARS[char]
    # 有些截图整行都是「星 期 三」三个单字，不受 x 限制
    singles = [item.text.strip() for item in row if len(item.text.strip()) == 1]
    if "星" in singles and "期" in singles:
        for char in singles:
            if char in _WEEKDAY_CHARS:
                return _WEEKDAY_CHARS[char]
    return None


def _is_course_title(text: str) -> bool:
    """课名行：不以任何字段标签开头，且含中文，长度适中。"""
    value = text.strip().rstrip("←→◆◇●○")
    if not value or len(value) < 2:
        return False
    if re.match(r"^(?:周数|上课地点|场地|地点|教师|老师|校区|教学班|考核方式|选课备注|课程学时)", value):
        return False
    if not re.search(r"[\u4e00-\u9fff]", value):
        return False
    return True


def _title_of(text: str) -> str:
    value = text.strip()
    value = re.sub(r"[\s]*[←→◆◇●○]+$", "", value)
    value = re.sub(r"[◆◇●○]", "", value)
    return value.strip()


def _field_row(source: str) -> dict[str, str]:
    """从字段行里取周数/地点/教师。"""
    out: dict[str, str] = {}
    match = _RE_WEEKS.search(source) or _RE_WEEKS_FUZZY.search(source)
    if match:
        weeks = match.group(1).replace("周", "").strip(" ,，、")
        # 只保留「数字 + 分隔符」的形式（OCR 可能把「前」等噪声带进来）
        weeks = re.sub(r"[^\d,\-—–~，、]", "", weeks)
        if weeks:
            out["weeks"] = weeks
    match = _RE_PLACE.search(source)
    if match:
        out["place"] = match.group(1).strip()
    match = _RE_TEACHER.search(source)
    if match:
        teacher = match.group(1).strip()
        teacher = re.split(r"[（(，,、;；]", teacher)[0]
        if len(teacher) <= 8:
            out["teacher"] = teacher
    return out


def _periods_of(row: Sequence[_Item]) -> tuple[int, int] | None:
    """从行首那一列取节次（``1-2`` / ``3-4`` / ``6-8``）。"""
    for item in row[:2]:
        match = _RE_PERIODS.match(item.text)
        if match:
            low, high = int(match.group(1)), int(match.group(2))
            return (low, high) if low <= high else (high, low)
    return None


def _scan_weekday_column(items: Sequence[_Item], x_limit: float) -> dict[float, int]:
    """扫描左侧竖排星期列，返回 ``{(星期块起始 y, 星期)}``。

    这是照片版式的关键：星期不是「星期三」连写，而是**竖排三个字**
    （「星」/「期」/「三」），且**跨视觉行**——实测「星期」在 y=62、「三」在 y=115。

    实现要点：
    * 只扫左侧窄条（x <= x_limit）；
    * 一个「星期」组的起始 y = 该组里「星」的 y（用它向上继承归属）；
    * 星期字可能在下一个块里，也可能是被 OCR 认错的字
      （photo3 里「星期」两行后面干脆没有独立星期字），
      所以缺字时**顺序推断**：按出现顺序依次给 一二三四五六日，跳过已出现过的。
    """
    left = sorted((item for item in items if item.x <= x_limit), key=lambda i: i.y)
    groups: list[dict] = []
    for item in left:
        text = item.text.strip()
        match = re.search(r"[一二三四五六日天]", text)
        is_week_head = "星" in text or text == "星期"
        if is_week_head:
            # 「星期X」连写：本块里就带星期字
            direct = match.group(0) if match else ""
            groups.append({"y": item.y, "direct": direct, "found": ""})
        elif groups and not groups[-1]["found"]:
            # 竖排的星期名单独成块（「三」「四」），或跟在「星期」之后
            if text in _WEEKDAY_CHARS:
                groups[-1]["found"] = text
            elif match and text not in ("星", "期"):
                # 「四 摄影艺术概论←」这种连写块：取开头的星期字
                if text[0] in _WEEKDAY_CHARS and groups[-1]["found"] == "":
                    groups[-1]["found"] = text[0]

    mapping: dict[float, int] = {}
    used: set[int] = set()

    # 第一轮：能直接读出星期字的组（优先用「星期三」连写，其次用单字）
    for group in groups:
        value = 0
        if group["direct"]:
            value = _WEEKDAY_CHARS[group["direct"]]
        elif group["found"]:
            value = _WEEKDAY_CHARS[group["found"]]
        if value and value not in used:
            mapping[group["y"]] = value
            used.add(value)

    # 第二轮：缺字的组按**顺序**补齐。
    # 实测 photo1 第一组是「星期」连写但没跟星期字、photo2 第三组缺、photo3 两组都缺。
    # 截图总是按星期顺序自上而下排列，所以「填最小的未用值」是最稳的推断。
    remaining = [d for d in range(1, 8) if d not in used]
    previous = 0
    for group in groups:
        if group["y"] in mapping:
            previous = mapping[group["y"]]
            continue
        if not remaining:
            break
        # 只取比上一组大的值（保证单调递增）
        candidate = next((d for d in remaining if d > previous), remaining[0])
        mapping[group["y"]] = candidate
        remaining.remove(candidate)
        previous = candidate
    return mapping


def parse_blocks(blocks: Sequence[dict[str, Any]], *, source: str = "photo",
                 width: float = 0.0, progress: Any = None) -> ImportResult:
    """解析「列表视图」OCR 结果。

    ``blocks`` 是 ``[{"text": …, "x": …, "y": …}, …]``（通常来自
    :func:`labkit.ttimport.ocr.load_engine` 的 ``placed``）。
    ``width`` 是图片宽度，用于定位「左侧星期列」。

    版式结构（三张照片实测一致）::

        课名行    马克思主义基本原理←
        字段行    [节次]  周数：1-16周  校区：下沙  上课地点：C208  教师：郭飞  教学班：…
        学时行    课程学时组成：理论：40，实习：8  周学时：3  总学时：48  学分：3.0

    所以：**课名行只出名字，节次/周次/地点/教师都在下一行**。
    """
    result = ImportResult(source=source)
    items = [_Item(text=str(b.get("text", "")), x=float(b.get("x", 0)),
                   y=float(b.get("y", 0))) for b in blocks if str(b.get("text", "")).strip()]
    if not items:
        result.warnings.append("这张图没有识别到任何文字。")
        result.finalize()
        return result

    min_x = min(item.x for item in items)
    # 左侧星期列很窄（实测星期字 x≈41-44，节次列 x≈135）：
    # 用 min_x 的两倍而不是图宽的 15%（后者会把节次列也划进左侧区）
    limit = max(min_x * 2.2, 60.0) if width <= 0 else max(min_x * 2.2, 60.0)
    weekday_rows = _scan_weekday_column(items, limit)
    result.meta["xLimit"] = round(limit, 1)
    result.meta["weekdayRows"] = len(weekday_rows)

    rows = _cluster_rows(items)
    result.meta["rows"] = len(rows)

    progress = as_progress(progress, text=f"解析列表视图 {source}")
    steps = max(1, len(rows))

    def tick(text: str = "") -> None:
        if progress is not None:
            progress.advance(1.0 / steps, text=text or progress.text)

    if progress is not None and rows:
        progress.set(0.0, text=f"解析列表视图 {source}")
        progress.advance(1.0 / steps, text="整理文字行")

    weekday = 1
    weekday_at_y = sorted(weekday_rows.items())
    pending_title: str | None = None
    pending_periods: tuple[int, int] | None = None
    found_weekdays: list[int] = []

    def weekday_for(y: float) -> int:
        """取「y 之下最近的星期行」——竖排星期字标在栏首，向下生效。

        实测三张照片：竖排「星期三」的「星」落在该栏第一行（或稍前），
        所以栏内所有课程的 y 都**大于等于**该标记；用向上继承会把栏首课程
        错挂到上一栏（photo1 的商务英语写作(1) 被归到周三，实际是周四）。
        """
        last = weekday
        for position, value in weekday_at_y:
            if position >= y:
                return value
            last = value
        return last

    for row in rows:
        tick()
        joined = _join(row)
        row_y = row[0].y

        # 1) 该行属于哪个星期（竖排星期列，向上继承）
        current_day = weekday_for(row_y)
        if current_day != weekday:
            weekday = current_day
            found_weekdays.append(current_day)

        # 2) 先判字段行：字段行里必然含「教学班/校区/考核方式」这些词，
        #    如果先过 _is_noise，整行会被误杀（实测踩过：周次全部丢失）。
        periods = _periods_of(row)
        has_fields = bool(re.search(r"(?:周数|上课地点|场地|教师)\s*[:：]", joined))

        if has_fields and pending_title:
            data = _field_row(joined)
            low, high = periods or (1, 2)
            result.courses.append(
                DraftCourse(
                    name=pending_title,
                    teacher=data.get("teacher", ""),
                    location=data.get("place", ""),
                    day=weekday,
                    start=low,
                    end=high,
                    mode="custom" if data.get("weeks") else "all",
                    weeks_text=data.get("weeks", ""),
                    source=source,
                    raw=joined,
                )
            )
            pending_title = None
            pending_periods = None
            continue

        # 3) 不含字段标签的行才做噪声判定。
        #    注意判「这一行的有效块是否全为噪声」——工具栏块（输出PDF/表格/列表）
        #    会和课名同处一行，整行拼起来看会被误判为噪声。
        effective = [
            item for item in row
            if not _is_noise(item.text.strip()) and not _is_toolbar(item.text.strip())
        ]
        if not effective:
            continue

        # 5) 课名行：剔除星期竖排字、节次块、学时统计块、右上角工具栏
        candidates = []
        for item in row:
            text = item.text.strip()
            if item.x <= limit and (text in _WEEKDAY_CHARS or text in ("星", "期")):
                continue
            if len(text) == 1 and text in _WEEKDAY_CHARS:
                continue
            if _RE_PERIODS.match(text):
                continue
            if _is_toolbar(text):
                continue
            if _is_noise(text):
                continue
            candidates.append(text)

        title = _title_of(" ".join(candidates)) if candidates else ""
        if title and _is_course_title(title):
            pending_title = title
            pending_periods = periods

    if pending_title:
        # 末尾落单的课名（缺字段行）：照样输出，教师/地点留空
        low, high = pending_periods or (1, 2)
        result.courses.append(
            DraftCourse(
                name=pending_title,
                teacher="",
                location="",
                day=weekday,
                start=low,
                end=high,
                mode="all",
                weeks_text="",
                source=source,
                raw=pending_title,
            )
        )
        result.warnings.append(f"「{pending_title}」这一行没有解析出周次/教师/地点，已留空。")

    result.meta["weekdays"] = sorted(set(found_weekdays))
    if progress is not None:
        progress.set(1.0, text="列表视图识别完成")
    result.finalize()
    return result


def parse_image_list(path: str, *, source: str = "photo", progress: Any = None) -> ImportResult:
    """对一张列表视图截图做 OCR 并解析。

    ``progress`` 接收 :class:`labkit.ttimport.progress.Progress`；
    调用方若已经做过 OCR（``parse_blocks`` 直接传入 ``blocks``），可省去这一步。
    """
    from . import ocr as ocr_mod

    progress = as_progress(progress, text="识别图片")
    recognize = ocr_mod.load_engine()
    image = ocr_mod.load_image(path)
    placed = getattr(recognize, "placed", None)
    if placed is not None:
        raw = placed(image)
        blocks = [{"text": text, "x": x, "y": y} for text, x, y in raw]
    else:
        blocks = [{"text": text, "x": 0.0, "y": float(index * 40)}
                  for index, text in enumerate(recognize(image))]
    if progress is not None:
        progress.advance(0.5, text="OCR 完成，开始解析")
    info = {"width": int(image.shape[1]), "height": int(image.shape[0])}
    return parse_blocks(blocks, source=source, width=float(info["width"]), progress=progress)


__all__ = ["parse_blocks", "parse_image_list"]
