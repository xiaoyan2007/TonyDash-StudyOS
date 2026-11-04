"""字段级识别规则（文本与 OCR 共用）。

所有判断都是**纯函数**，方便单元测试；也是将来适配别的学校时唯一要改的地方。
规则来自对 `ghvv-y/timetable-reminder` 的 `cell_parser.dart` / `paste_parser.dart`
逐行精读后重新组织，并修掉了它踩过的坑（详见各函数注释）。
"""

from __future__ import annotations

import re

from .weeks import EVEN_WORDS, ODD_WORDS

# --------------------------------------------------------------- 基础正则
RE_WEEKDAY = re.compile(r"(?:星期|周)\s*([一二三四五六日天])")
RE_WEEKDAY_EN = re.compile(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w*\b", re.I)

RE_PERIOD_RANGE = re.compile(r"第?\s*(\d{1,2})\s*[-—–~～至到]\s*(\d{1,2})\s*节")
RE_PERIOD_SINGLE = re.compile(r"第\s*(\d{1,2})\s*节")
RE_PERIOD_BARE = re.compile(r"^\s*(\d{1,2})\s*节\s*$")

#: 周次必须带「周」字 —— 放宽到裸数字会把课程编号 `_29` 当成第 29 周（踩坑④）
RE_WEEKS_SUFFIX = re.compile(
    r"((?:\d{1,2}(?:\s*[-—–~～至到]\s*\d{1,2})?)(?:\s*[,，、.。·•]\s*\d{1,2}(?:\s*[-—–~～至到]\s*\d{1,2})?)*)\s*周"
)
RE_WEEK_SINGLE = re.compile(r"第?\s*(\d{1,2})\s*周")

RE_ROOM = re.compile(r"[A-Za-z]\d{1,4}\s*[-—–]\s*\d{1,3}")
RE_ROOM_SIMPLE = re.compile(r"^[A-Za-z]?\d{1,4}[-—–]\d{1,4}$")

#: 「(单)」「单周」「双周」这类单双周标记，识别完要从文本里挖掉，
#: 否则会残留成课程名的一部分
RE_PARITY_TAG = re.compile(r"[(（]\s*[单双]\s*[)）]|单双周|单周|双周|单数周|双数周|奇数周|偶数周")

# --------------------------------------------------------------- 地点判定
#: 含这些字的几乎一定是上课地点（适配他校只改这两个元组）
PLACE_WORDS = ("楼", "馆", "厅", "室", "操场", "报告", "园", "号", "区", "中心", "场")
PLACE_PREFIXES = ("校本部", "本部", "北校", "南校", "东校", "西校", "学校", "新校")
PLACE_SUFFIXES = ("教室", "实验室", "机房", "多媒体", "阶梯")

#: 无意义的单元格噪声
NOISE_WORDS = ("无", "空", "—", "-", "/", "\\", "暂无", "待定", "未安排", "无课")

#: 星期表头（OCR 会把表头当成课程内容）
WEEKDAY_HEADERS = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六",
                   "星期日", "星期天", "周一", "周二", "周三", "周四", "周五",
                   "周六", "周日", "周天", "星期一~日")

#: 时间/节次栏表头
PERIOD_HEADERS = ("节次", "时间", "上午", "下午", "晚上", "第一节", "作息")


def clean(text: str) -> str:
    """清掉 OCR 常见的零宽字符、多余空白与装饰符。"""
    if not text:
        return ""
    out = str(text).replace("\u200b", "").replace("\ufeff", "")
    out = out.replace("＊", "*").replace("．", ".").replace("：", ":")
    out = re.sub(r"[ \t\u00a0]+", " ", out)
    return out.strip()


def is_noise(text: str) -> bool:
    """是否是「无课/空白」这类噪声。"""
    value = clean(text)
    if not value:
        return True
    if value in NOISE_WORDS:
        return True
    # 只剩标点或单个符号
    if not re.search(r"[0-9A-Za-z\u4e00-\u9fa5]", value):
        return True
    return False


def is_weekday_header(text: str) -> bool:
    value = clean(text)
    if not value:
        return False
    if value in WEEKDAY_HEADERS:
        return True
    if RE_WEEKDAY.fullmatch(value) or RE_WEEKDAY_EN.fullmatch(value):
        return True
    # 「周1」这种阿拉伯数字写法也算表头。
    # 注意：**不能**写 `value.startswith("周")` —— 周是常见姓氏，
    # 「周九」这样的老师名字会被当成表头丢掉（实测踩到过）。
    return bool(re.fullmatch(r"周\s*[1-7]", value))


def is_period_header(text: str) -> bool:
    value = clean(text)
    if not value:
        return False
    if value in PERIOD_HEADERS:
        return True
    return any(value.startswith(head) for head in ("节次", "时间", "午", "晚"))


def looks_like_place(text: str) -> bool:
    """是否像上课地点。

    必须**先于**课程名判定（踩坑①）：否则「教学楼A202」会被当成课程名，
    导致同一门课被拆成两条。
    """
    value = clean(text)
    if not value or len(value) > 30:
        return False
    if value.startswith(PLACE_PREFIXES):
        return True
    if any(word in value for word in PLACE_WORDS):
        return True
    if any(word in value for word in PLACE_SUFFIXES):
        return True
    if RE_ROOM.search(value):
        return True
    if RE_ROOM_SIMPLE.match(value):
        return True
    # 纯「字母 + 数字」的房间号（A202 / B-301）
    if re.fullmatch(r"[A-Za-z]{1,3}\d{1,4}[A-Za-z]?", value):
        return True
    if re.fullmatch(r"\d{1,4}[-—–]\d{1,4}", value):
        return True
    return False


def looks_like_teacher(text: str) -> bool:
    """是否像教师姓名。

    仅看形态；调用方必须再确认「已经收集到课程名」（踩坑②），
    否则「体育」这种两字课名会被当成人名，整门课丢失。
    """
    value = clean(text)
    if not value:
        return False
    if re.fullmatch(r"[\u4e00-\u9fa5]{2,4}", value):
        return True
    # 「张三,李四」「张三 王五」
    if re.fullmatch(r"[\u4e00-\u9fa5]{2,4}([、,，/ ][\u4e00-\u9fa5]{2,4})+", value):
        return True
    # 带职称：「张三(教授)」「李四 副教授」
    if re.fullmatch(r"[\u4e00-\u9fa5]{2,4}\s*[（(]?(教授|副教授|讲师|助教|老师)[)）]?", value):
        return True
    return False


def extract_weekday(text: str) -> int | None:
    """取星期几（1=周一 … 7=周日）；取不到返回 ``None``。"""
    value = clean(text)
    match = RE_WEEKDAY.search(value)
    if match:
        char = match.group(1)
        return 7 if char in ("日", "天") else "一二三四五六".index(char) + 1
    match = RE_WEEKDAY_EN.search(value)
    if match:
        table = {"mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 7}
        return table[match.group(1)[:3].lower()]
    return None


def extract_periods(text: str) -> tuple[int, int] | None:
    """取节次范围；单节返回 ``(n, n)``。"""
    value = clean(text)
    match = RE_PERIOD_RANGE.search(value)
    if match:
        low, high = int(match.group(1)), int(match.group(2))
        return (low, high) if low <= high else (high, low)
    match = RE_PERIOD_SINGLE.search(value)
    if match:
        return int(match.group(1)), int(match.group(1))
    match = RE_PERIOD_BARE.match(value)
    if match:
        return int(match.group(1)), int(match.group(1))
    return None


def extract_weeks_text(text: str) -> str:
    """抽出周次片段原文（可能含多段，如 ``3-4,6-10``）。"""
    value = clean(text)
    if "周" not in value:
        return ""
    parts = [m.group(1) for m in RE_WEEKS_SUFFIX.finditer(value)]
    if parts:
        return ",".join(parts)
    match = RE_WEEK_SINGLE.search(value)
    if match:
        return match.group(1)
    return ""


def extract_parity(text: str) -> str:
    """识别单/双周信息，返回 ``"odd"`` / ``"even"`` / ``""``。

    单独抽出来是因为「1-15周(单)」里的括号信息位于周次片段之外，
    只靠 :func:`extract_weeks_text` 会丢掉，进而在导出时只剩 ``1-15``，
    整学期的单周课就被错误地变成「1-15 周每周都上」。
    """
    value = clean(text)
    if not value:
        return ""
    if "单双" in value:
        return ""
    if any(word in value for word in ODD_WORDS):
        return "odd"
    if any(word in value for word in EVEN_WORDS):
        return "even"
    if re.search(r"[(（]\s*单\s*[)）]", value) or re.search(r"周\s*单\b", value):
        return "odd"
    if re.search(r"[(（]\s*双\s*[)）]", value) or re.search(r"周\s*双\b", value):
        return "even"
    return ""


def strip_fields(text: str) -> str:
    """把已识别的星期/节次/周次片段从文本里挖掉，剩下课名/教师/地点候选。"""
    value = clean(text)
    value = RE_PERIOD_RANGE.sub(" ", value)
    value = RE_PERIOD_SINGLE.sub(" ", value)
    value = RE_WEEKS_SUFFIX.sub(" ", value)
    value = RE_PARITY_TAG.sub(" ", value)
    value = RE_WEEKDAY.sub(" ", value)
    value = RE_WEEKDAY_EN.sub(" ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" \t,，、;；|/-—–")


def to_minutes(value: str) -> int:
    """``"08:05"`` → ``485``。解析不出来时返回 0（调用方按 0 处理即可）。"""
    hour, _, minute = str(value).partition(":")
    try:
        return int(hour) * 60 + int(minute or 0)
    except ValueError:
        return 0


__all__ = [
    "RE_WEEKDAY", "RE_PERIOD_RANGE", "RE_PERIOD_SINGLE", "RE_WEEKS_SUFFIX",
    "PLACE_WORDS", "PLACE_PREFIXES", "NOISE_WORDS", "WEEKDAY_HEADERS",
    "clean", "is_noise", "is_weekday_header", "is_period_header",
    "looks_like_place", "looks_like_teacher", "to_minutes",
    "extract_weekday", "extract_periods", "extract_weeks_text", "extract_parity",
    "strip_fields",
]
