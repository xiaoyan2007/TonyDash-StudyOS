"""PDF 课表解析 —— 面向「文字型」教务系统导出 PDF（不是扫描件）。

本项目的 material 里的 PDF 已实测清楚，实现方式由三个事实决定：

1. **页面旋转 90°**（mediabox 595×842，显示 rect 842×595）。``get_text`` 的坐标
   仍在未旋转坐标系里，于是：

   * **y 轴 = 星期**：第 1 页表头中心 y = 691(一) / 587(二) / 483(三) / 379(四) / 276(五) / 172(六) / 68(日)
   * **x 轴 = 节次**：节次标号中心 x 从 84(第1节) 递增到 564(第9节)；第 2 页是「晚上」行的续页

2. **每门课的文字自带结构化字段**，形如::

       综合商务英语(3)◆
       (1-2节)1-16周/校区:下沙/场
       地:外语楼233/教师:郭虹宇
       /教学班:…

   课名、节次、周次、场地、教师**全在文字里**，正则 100% 可抽。

3. **归行只能按 y 就近到星期表头，不能按节次分列再落格**。实测分列会把同一门课的
   块拆到相邻两列（`跨境电商营销与大数据` 和 `分析` 被拆开），因为课程块横跨
   多个节次列。正确做法：**同一行（同一个星期）内的块按 x 全排序拼成一整串**，
   节次信息交给 `(X-Y节)` 锚点自己带出来。

跨页续行：第 2 页没有星期表头，此时**沿用上一页的行归属**（内容按 y 顺序继续
落到最近的已建立行），这样被分页切断的课程仍然完整。

扫描件（没有文字层）自动退化成「渲染成图再走截图 OCR」。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import DraftCourse, ImportResult
from .progress import as_progress

try:  # pymupdf 在全局与 lab/.venv 都有
    import pymupdf as _fitz
except Exception:  # noqa: BLE001 - 老版本只提供 fitz 这个名字
    try:
        import fitz as _fitz  # type: ignore
    except Exception:  # noqa: BLE001
        _fitz = None

WEEKDAY_HEAD = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")

#: 课程类型符号（◆ 理论 / ◇ 实验 / ● 实习 / ○）
_COURSE_MARK = "◆◇●○"
_MARK_CLASS = "[" + _COURSE_MARK + "]"

#: 一门课的开头：`(1-2节)` / `(6-8节)`（吃全角括号与各种连字符）
_RE_PERIOD_RANGE = re.compile(r"[(（]\s*(\d{1,2})\s*[-—–~～至]\s*(\d{1,2})\s*节\s*[)）]")
_RE_PERIOD_SINGLE = re.compile(r"[(（]\s*(\d{1,2})\s*节\s*[)）]")

#: 周次数字部分（后跟「周」）。用负向断言排除学分小数（`4.0`）
_RE_WEEKS_PART = re.compile(r"(?<![\d.])[\d]+(?:[,\-—–~，、]+[\d]+)*(?=\s*周)")

#: 字段抽取
_RE_PLACE = re.compile(r"(?:场地|上课地点|地点)\s*[:：]\s*([^/／]*)")
_RE_TEACHER = re.compile(r"(?:教师|老师)\s*[:：]\s*([^/／]*)")

#: 分隔字段用的是 `/`，字段名以这些词开头
_FIELD_SPLIT = re.compile(
    r"/(?=(?:教学班|教学班组成|考核方式|选课备注|课程学时组成|周学时|总学时|学分|校区|场地|教师|学时|备注))"
)

#: 硬字段（没有前导 `/`，直接粘在课名前的）
_HARD_FIELD = re.compile(
    r"(?:教学班组成|教学班|考核方式|选课备注|课程学时组成|周学时|总学时|学分)\s*[:：]"
)

#: 整块丢弃：表头、页脚、标题、时间段
_NOISE = (
    re.compile(r"^时间段"),
    re.compile(r"^节次"),
    re.compile(r"打印时间"),
    re.compile(r"学号"),
    re.compile(r"课\s*表"),          # 「严宇轩课表」这类标题
    re.compile(r"^[◆◇●○]\s*[:：]"),  # 图例
    re.compile(r"^(上午|下午|晚上)$"),
)


class PdfUnavailable(RuntimeError):
    """没有 pymupdf，或这个 PDF 解不出来。"""


@dataclass
class _Block:
    """一个文本块。"""

    page: int
    x0: float
    x1: float
    y0: float
    y1: float
    text: str

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


# --------------------------------------------------------------------------- 依赖
def available() -> tuple[bool, str]:
    """PDF 解析是否可用。"""
    if _fitz is None:
        return False, "缺少 pymupdf：py -3 -m pip install pymupdf"
    return True, f"pymupdf {getattr(_fitz, '__version__', '?')} 可用"


def _open(path: Path):
    if _fitz is None:
        raise PdfUnavailable(available()[1])
    if not path.is_file():
        raise PdfUnavailable(f"文件不存在：{path}")
    try:
        return _fitz.open(str(path))
    except Exception as exc:  # noqa: BLE001
        raise PdfUnavailable(f"打开 PDF 失败：{type(exc).__name__}: {exc}") from exc


# --------------------------------------------------------------------------- 版面
def _weekday_centers(page) -> dict[int, float]:
    """星期表头中心 y。用 ``get_text("words")`` 拿独立坐标（块内顺序不可靠）。"""
    found: dict[int, float] = {}
    for word in page.get_text("words"):
        text = word[4]
        if text not in WEEKDAY_HEAD:
            continue
        found.setdefault(WEEKDAY_HEAD.index(text) + 1, (word[1] + word[3]) / 2)
    return found


def _block_text(block) -> str:
    return "".join(
        span["text"] for line in block.get("lines", []) for span in line.get("spans", [])
    ).strip()


def _is_noise(text: str) -> bool:
    if not text:
        return True
    if re.fullmatch(r"\d{1,2}", text):  # 节次标号
        return True
    if any(name in text for name in WEEKDAY_HEAD) and len(text) <= 40:
        return True  # 表头块
    return any(pattern.search(text) for pattern in _NOISE)


def _collect(page, number: int) -> list[_Block]:
    """收集正文块（剔除表头/页脚）。"""
    out: list[_Block] = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        text = _block_text(block)
        if _is_noise(text):
            continue
        x0, y0, x1, y1 = block["bbox"]
        out.append(_Block(page=number, x0=x0, x1=x1, y0=y0, y1=y1, text=text))
    return out


def _row_bounds(centers: dict[int, float], height: float) -> list[tuple[int, float, float]]:
    """把星期中心排序成「行区间」``[(星期, 上界, 下界)]``。

    第 1 页实测顺序（从上到下）：日(68) 六(172) 五(276) 四(379) 三(483) 二(587) 一(691)。
    """
    ordered = sorted(centers.items(), key=lambda item: item[1])
    bounds: list[tuple[int, float, float]] = []
    for index, (day, y) in enumerate(ordered):
        upper = -1e9 if index == 0 else (ordered[index - 1][1] + y) / 2
        lower = 1e9 if index == len(ordered) - 1 else (y + ordered[index + 1][1]) / 2
        bounds.append((day, upper, lower))
    return bounds


# --------------------------------------------------------------------------- 文本工具
def _squash(text: str) -> str:
    """去掉所有空白（PDF 里中文常被逐字断行）。"""
    return re.sub(r"[ \t\u3000]+", "", text)


def _strip_name(head: str) -> str:
    """从「上一条目字段尾巴 + 课名」里取出课名。

    实测尾巴形如 ``:32/学分:2.0``；也可能是 ``.03``（小数被断行切到了下个块开头）。
    所以：按 ``/字段`` 取最后一段 → 按硬字段切 → 剥掉前导的标点/数字/类型符号。
    """
    parts = [part for part in _FIELD_SPLIT.split(head) if part]
    tail = parts[-1] if parts else head
    tail = _HARD_FIELD.split(tail)[-1]
    tail = re.sub(r"^[\d.．:：/／，,、\s]+", "", tail)
    tail = re.sub(_MARK_CLASS, "", tail)
    return tail.strip(" /／、，,;；")


def _extract_weeks(tail: str) -> str:
    """抽周次文本：``1-16`` / ``13`` / ``4,16,19-20``。"""
    parts = _RE_WEEKS_PART.findall(_squash(tail))
    cleaned = [part.strip(",，、") for part in parts if part.strip(",，、")]
    if not cleaned:
        return ""
    return re.sub(r",+", ",", ",".join(cleaned)).strip(",")


def _clean_teacher(text: str) -> str:
    """教师名清理：去职称括号、被下一字段污染的部分、异常长串。"""
    text = text.strip()
    text = re.split(r"[（(，,、;/／]|校区|场地|教学班|考核方式|学分", text)[0].strip()
    if len(text) > 8 or not text:
        return ""
    return text


#: 常见中文姓氏（只取最常见的，用来判断「末尾这几个字是不是人名」）
_SURNAMES = set("赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
                "戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐"
                "费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平"
                "黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝"
                "董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊"
                "胡凌霍虞万支柯昝管卢莫 _经房裘缪干解应宗丁宣邓郁单杭洪包诸左石"
                "崔吉钮龚程嵇邢滑裴陆荣翁荀羊於惠甄回家封芮羿储靳汲邴糜松井段富"
                "巫乌焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘钭厉戎祖武"
                "符刘景詹束龙叶幸司韶郜黎蓟薄印宿白怀蒲邰从鄂索咸籍赖卓蔺屠蒙池"
                "乔阴胥能苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍却璩桑桂濮牛寿通边"
                "扈燕冀郏浦尚农温别庄晏柴瞿阎充慕连茹习宦艾鱼容向古易慎戈廖庾终"
                "暨居衡步都耿满弘匡国文寇广禄阙东欧殳沃利蔚越夔隆师巩厍聂晁勾敖"
                "融冷訾辛阚那简饶空曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益"
                "桓公庹")

#: 不是人名的常见「课程名尾字」（避免把「实训」「理论」当成人名）
_NOT_NAME_TAIL = ("实训", "理论", "实验", "实习", "劳动", "基础", "导论", "概论",
                  "实践", "课程", "双语", "写作", "阅读", "听说", "视听说")


def _teacher_tail(name: str) -> str:
    """从课程名末尾猜出教师名（2~4 字，以常见姓氏开头）。"""
    for length in (3, 2, 4):
        if len(name) <= length + 1:
            continue
        tail = name[-length:]
        if any(bad in tail for bad in _NOT_NAME_TAIL):
            continue
        if tail[0] in _SURNAMES and all("\u4e00" <= ch <= "\u9fff" for ch in tail):
            return tail
    return ""


def _looks_like_teacher_tail(name: str) -> bool:
    return bool(_teacher_tail(name))


# --------------------------------------------------------------------------- 切课
def _split_courses(text: str, weekday: int, *, source: str) -> list[DraftCourse]:
    """用 ``(X-Y节)`` 锚点把「一个星期的阅读序文本」切成课程。"""
    text = _squash(text)
    if not text:
        return []

    marks: list[tuple[int, int, int, int]] = []
    for match in _RE_PERIOD_RANGE.finditer(text):
        marks.append((match.start(), match.end(), int(match.group(1)), int(match.group(2))))
    for match in _RE_PERIOD_SINGLE.finditer(text):
        marks.append((match.start(), match.end(), int(match.group(1)), int(match.group(1))))
    marks.sort()
    if not marks:
        return []

    courses: list[DraftCourse] = []
    seen: set[tuple[str, int, int]] = set()
    for index, (start, end, first, last) in enumerate(marks):
        head_start = marks[index - 1][1] if index else 0
        name = _strip_name(text[head_start:start])
        if not name or len(name) < 2:
            continue

        tail_end = marks[index + 1][0] if index + 1 < len(marks) else len(text)
        tail = text[end:tail_end]

        weeks_text = _extract_weeks(tail)
        place_match = _RE_PLACE.search(tail)
        place = place_match.group(1).strip() if place_match else ""
        teacher_match = _RE_TEACHER.search(tail)
        teacher = _clean_teacher(teacher_match.group(1)) if teacher_match else ""

        low, high = (first, last) if first <= last else (last, first)
        key = (name, low, high)
        if key in seen:
            continue
        seen.add(key)

        courses.append(
            DraftCourse(
                name=name,
                teacher=teacher,
                location=place,
                day=int(weekday),
                start=low,
                end=high,
                mode="custom" if weeks_text else "all",
                weeks_text=weeks_text,
                source=source,
                raw=f"{name}|{low}-{high}|{weeks_text}|{place}|{teacher}",
            )
        )
    return courses


def _extras_start(page) -> float | None:
    """页脚「实践课程/其他课程」区块的 x 起点（x 才是阅读方向）。

    实测：这段文字出现在 y 轴末端（图例「◆: 理论」那一段所在行），
    在 x 方向上位于最右。取它的最小 x 作为分界，x 大于等于这个值的块归 extras，
    主流程里不再参与课程切分——否则里面的 `19-20周` 会被错挂到上一门课上。
    """
    xs: list[float] = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        text = _block_text(block)
        if "实践课程" in text or "其他课程" in text:
            xs.append(block["bbox"][0])
    return min(xs) if xs else None


def _is_extras_text(text: str) -> bool:
    """是不是页脚 extras 区块的文本。"""
    return ("实践课程" in text or "其他课程" in text
            or "共" in text and "周" in text
            or "◆:" in text or "◇:" in text or "图例" in text)


def _parse_extras(text: str, *, source: str) -> list[DraftCourse]:
    """解析末尾「实践课程 / 其他课程」这类不走节次表的条目。

    实测格式::

        实践课程：商务英语专业认知实践●刘瑜(共2周)/12-13周;
        其他课程：创业基础实训(文)刘宇慧(共8周)/1-8周/无;

    这些条目**没有节次**，星期与具体时间都缺：照样输出，但标 issue 让用户在
    预览里确认；教师缺失时留空。
    """
    out: list[DraftCourse] = []
    text = _squash(text)
    for block in re.split(r"(?:实践课程|其他课程)\s*[:：]", text):
        block = block.strip(" ;；")
        if not block:
            continue
        for chunk in re.split(r"[;；]", block):
            chunk = chunk.strip(" /／")
            if not chunk:
                continue
            match = re.match(r"(.+?)[(（]共\d+周[)）]", chunk)
            if not match:
                continue
            head = re.sub(_MARK_CLASS, "|", match.group(1))
            name, _, teacher = head.partition("|")
            if not teacher:
                # 「创业基础实训(文)刘宇慧」这种没有 ● 符号的：末尾 2~4 个汉字算教师。
                plain = name.strip(" /／、，,;；")
                tail = _teacher_tail(plain)
                if tail:
                    teacher = tail
                    name = plain[: len(plain) - len(tail)]
            name = name.strip(" /／、，,;；")
            teacher = _clean_teacher(teacher)
            if len(name) < 2:
                continue
            weeks_text = _extract_weeks(chunk[match.end():])
            course = DraftCourse(
                name=name,
                teacher=_clean_teacher(teacher),
                location="",
                day=1,
                start=1,
                end=2,
                mode="custom" if weeks_text else "all",
                weeks_text=weeks_text,
                source=source,
                raw=chunk,
            )
            course.issues.append("这条没有固定节次（实践/其他课程），星期与时间需确认")
            out.append(course)
    return out


# --------------------------------------------------------------------------- 主流程
def parse_pdf(path: str | Path, *, source: str = "pdf",
              progress: Any = None) -> ImportResult:
    """解析文字型课表 PDF；扫描件自动退化到 OCR。

    ``progress`` 接收 :class:`labkit.ttimport.progress.Progress`，
    按页分摊回报。
    """
    target = Path(path)
    result = ImportResult(source=source)
    doc = _open(target)
    per_day: dict[int, list[_Block]] = {}
    missing_header: list[int] = []
    page_count = 0
    extras_text = ""
    progress = as_progress(progress, text=f"读取 PDF {target.name}")
    try:
        page_total = max(1, len(doc))
        if progress is not None:
            progress.set(0.0, text=f"读取 PDF {target.name}")
        total_chars = 0
        for number, page in enumerate(doc, start=1):
            page_count = number
            total_chars += len((page.get_text() or "").strip())
            centers = _weekday_centers(page)
            blocks = _collect(page, number)
            height = float(page.rect.height)

            # 页脚「实践课程/其他课程」单独收走：它们不属于任何一星期，
            # 混进课程行会把 `19-20周` 这种周次错挂到上一门课上（实测踩过）。
            cut = _extras_start(page)
            if cut is not None:
                footer = [b for b in blocks if b.cx >= cut and _is_extras_text(b.text)]
                if footer:
                    extras_text += "".join(
                        b.text for b in sorted(footer, key=lambda b: (b.page, b.cx))
                    )
                    blocks = [b for b in blocks if b not in footer]

            if centers:
                bounds = _row_bounds(centers, height)
                for block in blocks:
                    day = min(
                        bounds,
                        key=lambda item: 0 if item[1] <= block.cy <= item[2]
                        else min(abs(block.cy - item[1]), abs(block.cy - item[2])),
                    )[0]
                    per_day.setdefault(day, []).append(block)
            else:
                # 没有表头（多为跨页续行）：沿用上一页的行归属。
                missing_header.append(number)
                known = {
                    day: sum(b.cy for b in items) / len(items)
                    for day, items in per_day.items()
                }
                for block in blocks:
                    day = min(known, key=lambda d: abs(known[d] - block.cy)) if known else 1
                    per_day.setdefault(day, []).append(block)

            if progress is not None:
                progress.advance(1.0 / page_total, text=f"第 {number}/{page_total} 页")

        result.meta["pages"] = page_count
        result.meta["textChars"] = total_chars

        if total_chars < 40:
            return _parse_via_ocr(target, result, progress=progress)
    finally:
        try:
            doc.close()
        except Exception:  # noqa: BLE001
            pass

    for day in sorted(per_day):
        blocks = sorted(per_day[day], key=lambda b: (b.page, b.cx, b.cy))
        text = "".join(block.text for block in blocks)
        result.courses.extend(_split_courses(text, day, source=source))

    # 页脚的实践/其他课程（已在收集阶段单独摘出，不混进任何星期）
    if extras_text:
        result.courses.extend(_parse_extras(extras_text, source=source))

    result.meta["mode"] = "pdf-text"
    if missing_header:
        result.warnings.append(
            f"第 {'、'.join(str(n) for n in missing_header)} 页没有星期表头（跨页续行），"
            "内容已按 y 顺序并入相邻星期的课表。"
        )

    if not result.courses:
        result.warnings.append("没从 PDF 里解析出课程，可能不是标准教务课表格式。")
    result.finalize()
    if progress is not None:
        progress.set(1.0, text="PDF 解析完成")
    return result


def _parse_via_ocr(path: Path, base: ImportResult, progress: Any = None) -> ImportResult:
    """扫描件 PDF：逐页渲染成图，走截图 OCR，再合并。"""
    from . import ocr as ocr_mod
    from ..common import paths

    if _fitz is None:
        raise PdfUnavailable(available()[1])
    base.warnings.append("这个 PDF 没有文字层（像是扫描件），已改用 OCR 识别。")
    merged = ImportResult(source="pdf-ocr")
    doc = _open(path)
    progress = as_progress(progress, text=f"OCR 识别 {path.name}")
    try:
        temp_dir = paths.ensure_dir(paths.DATA_DIR / "tmp" / "pdf-ocr")
        page_total = max(1, len(doc))
        if progress is not None:
            progress.set(0.0, text=f"OCR 识别 {path.name}")
        for number, page in enumerate(doc, start=1):
            pixmap = page.get_pixmap(matrix=_fitz.Matrix(3.0, 3.0))
            temp = temp_dir / f"{path.stem}-p{number}.png"
            pixmap.save(str(temp))
            try:
                page_progress = (progress.slice(1.0 / page_total)
                                 if progress is not None else None)
                one = ocr_mod.parse_image(str(temp), progress=page_progress)
            except Exception as exc:  # noqa: BLE001
                merged.warnings.append(f"第 {number} 页 OCR 失败：{type(exc).__name__}: {exc}")
                continue
            for course in one.courses:
                course.source = "pdf-ocr"
                course.issues.append(f"来自 PDF 第 {number} 页的 OCR 结果")
                merged.courses.append(course)
            merged.periods.extend(one.periods)
            merged.warnings.extend(one.warnings)
    finally:
        try:
            doc.close()
        except Exception:  # noqa: BLE001
            pass
    merged.finalize()
    merged.meta["mode"] = "pdf-ocr"
    if progress is not None:
        progress.set(1.0, text="扫描版 OCR 完成")
    return merged


__all__ = ["PdfUnavailable", "available", "parse_pdf"]
