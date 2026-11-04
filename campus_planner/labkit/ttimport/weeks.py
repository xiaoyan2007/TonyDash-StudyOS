"""周次表达式解析 —— 课表导入里最容易出错、也最值得打磨的一块。

移动端开源实现（timetable-reminder）的 `parseWeekExpr` 只保留数字、逗号和连字符，
因此**不支持中文数字，也不认识「单周/双周」字样**。主程序 `WeekSpec` 反而更宽：
`mode` 三档 + `custom` 任意文本，于是这里可以做三件更正确的事：

1. 认识「第三周」「十一至十六周」「每逢单周」这类真实教务写法；
2. 认出结果恰好等于全体/单数/双数时自动回落到 ``all``/``odd``/``even``，
   存进主程序后由主程序自己的周次逻辑驱动，而不是塞一坨 custom 文本；
3. 不连续周次（``3-4,6-10周``）**保持一条课程**，不拆成多条 —— 主程序支持。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: 中文数字 -> 阿拉伯数字（周次不会超过 99，只处理常用组合）
_CN_DIGIT = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
             "六": 6, "七": 7, "八": 8, "九": 9}

#: 全角 -> 半角（数字与常用标点）
_FULLWIDTH = {ord(c) + 0xFEE0: ord(c) for c in
              "0123456789,;:()-~"}
_FULLWIDTH.update({
    ord("，"): ord(","), ord("、"): ord(","), ord("；"): ord(";"),
    ord("—"): ord("-"), ord("–"): ord("-"), ord("－"): ord("-"),
    ord("～"): ord("-"), ord("至"): ord("-"), ord("到"): ord("-"),
    ord("（"): ord("("), ord("）"): ord(")"), ord("　"): ord(" "),
})

_SPLIT_RE = re.compile(r"[,;/\s]+")
#: OCR 常把「,」认成「.」「。」「、」「·」，只要夹在数字之间就按分隔符处理。
#: 只在数字之间生效，避免把「3.5学分」这类小数误改。
_SEP_FIX_RE = re.compile(r"(?<=\d)\s*[.。、·•]\s*(?=\d)")
_RANGE_RE = re.compile(r"^(\d{1,2})\s*-\s*(\d{1,2})$")
_SINGLE_RE = re.compile(r"^(\d{1,2})$")
#: 周次片段里的括号备注（``1-9(单)``、``3-4（双周）``）：解析前先摘掉
_PAREN_RE = re.compile(r"[(（][^)）]*[)）]")
_CN_NUM_RE = re.compile(r"[零一二两三四五六七八九十]{1,3}")

ODD_WORDS = ("单周", "奇数周", "每逢单", "逢单", "单数周")
EVEN_WORDS = ("双周", "偶数周", "每逢双", "逢双", "双数周")


def normalize(expr: str) -> str:
    """全角转半角、统一连接符、去掉无意义修饰词。"""
    if not expr:
        return ""
    text = str(expr).translate(_FULLWIDTH)
    text = _SEP_FIX_RE.sub(",", text)
    for noise in ("第", "周次", "周", "星期", "学期", "共", "上课", "上到",
                  "每", "逢", "的", "个", "全"):
        text = text.replace(noise, " ")
    return re.sub(r"\s+", " ", text).strip()


def cn_to_int(text: str) -> int | None:
    """把「十」「十六」「二十」「二十一」转成整数；无法解析返回 ``None``。"""
    text = text.strip()
    if not text:
        return None
    if "十" not in text:
        if len(text) == 1 and text in _CN_DIGIT:
            return _CN_DIGIT[text]
        return None
    head, _, tail = text.partition("十")
    tens = _CN_DIGIT.get(head, 1) if head else 1
    ones = _CN_DIGIT.get(tail, 0) if tail else 0
    if tail and tail not in _CN_DIGIT:
        return None
    return tens * 10 + ones


def _replace_cn_numbers(text: str) -> str:
    """把连续中文数字替换成阿拉伯数字。"""
    def _sub(match: re.Match) -> str:
        value = cn_to_int(match.group(0))
        return str(value) if value is not None else match.group(0)

    return _CN_NUM_RE.sub(_sub, text)


@dataclass
class WeekResult:
    """一次周次解析的结果。"""

    weeks: list[int] = field(default_factory=list)
    mode: str = "all"
    text: str = ""
    warnings: list[str] = field(default_factory=list)
    raw: str = ""

    @property
    def empty(self) -> bool:
        return not self.weeks

    def label(self, total: int = 0) -> str:
        """人类可读的周次描述，用于列表展示。"""
        if self.mode == "all":
            return "全周" if not total else f"1-{total} 周"
        if self.mode == "odd":
            return "单周"
        if self.mode == "even":
            return "双周"
        return f"{self.text} 周" if self.text else "（空）"


def compress_ranges(numbers) -> str:
    """把 ``[1,2,3,7,8]`` 压成 ``"1-3,7-8"``。与主程序 ``compress_ranges`` 同义。"""
    values = sorted({int(n) for n in numbers})
    if not values:
        return ""
    parts: list[str] = []
    start = prev = values[0]
    for value in values[1:]:
        if value == prev + 1:
            prev = value
            continue
        parts.append(f"{start}-{prev}" if start != prev else f"{start}")
        start = prev = value
    parts.append(f"{start}-{prev}" if start != prev else f"{start}")
    return ",".join(parts)


def infer_mode(weeks, total: int) -> tuple[str, str]:
    """判断这批周次是否恰好是全体/单数/双数。

    返回 ``(mode, custom_text)``。注意 ``total`` 必须是**整张课表的学期总周数**，
    而不是单门课的最大周数 —— 否则只上前 8 周的课会被误判成「全周」。
    """
    values = sorted({int(w) for w in weeks})
    if not values:
        return "all", ""
    total = int(total or 0)
    full = set(range(1, total + 1))
    if total > 0 and set(values) == full:
        return "all", ""
    if total > 0 and set(values) == set(range(1, total + 1, 2)):
        return "odd", ""
    if total > 0 and set(values) == set(range(2, total + 1, 2)):
        return "even", ""
    return "custom", compress_ranges(values)


def _split_glued(value: int, upper: int) -> list[int] | None:
    """把 OCR 吞掉分隔符后粘在一起的数字拆回两个，例如 ``46`` → ``[4, 6]``。

    只在**恰好一种**切分让两段都落在 ``1..upper`` 时才采用。理由：真实学期不会
    超过 ``upper`` 周，所以超出上限的 ``46`` 必然是 ``4`` 和 ``6`` 粘住了；而
    ``1016`` 有 ``1|016`` 与 ``10|16`` 两种可能，就宁可不动、按告警交给用户。
    """
    digits = str(int(value))
    if len(digits) < 2:
        return None
    fits: list[tuple[int, int]] = []
    for cut in range(1, len(digits)):
        left, right = int(digits[:cut]), int(digits[cut:])
        if 1 <= left <= upper and 1 <= right <= upper:
            fits.append((left, right))
    return list(fits[0]) if len(fits) == 1 else None


def _expand_token(token: str, upper: int) -> tuple[set[int], set[int], list[str]]:
    """把一个周次片段展开成集合。

    返回 ``(有效周次, 越界周次, 告警)``。范围端点被 OCR 粘住时会拆开并按
    「拆出的前一个单独成周 + 后一个接上范围」解释，例如 ``46-10`` → ``4`` 与
    ``6-10``，也就是 ``4,6,7,8,9,10``。
    """
    numbers: set[int] = set()
    bad: set[int] = set()
    notes: list[str] = []
    # 「3-46-10」= 逗号被 OCR 吞掉的「3-4,6-10」：三段、中间那段超上限且能拆开
    parts = [piece for piece in token.split("-") if piece]
    if len(parts) == 3 and all(piece.isdigit() for piece in parts):
        first, middle, last = (int(piece) for piece in parts)
        glue = _split_glued(middle, upper) if not (1 <= middle <= upper) else None
        if glue:
            left, right = glue
            notes.append(f"「{middle}」按 {left}、{right} 处理（分隔符可能被 OCR 吞掉）")
            for start, stop in ((first, left), (right, last)):
                numbers.update(range(min(start, stop), max(start, stop) + 1))
            return {n for n in numbers if 1 <= n <= upper}, set(), notes

    match = _RANGE_RE.match(token)
    if match:
        low, high = int(match.group(1)), int(match.group(2))
        is_range = True
    elif _SINGLE_RE.match(token):
        low = high = int(token)
        is_range = False
    else:
        return numbers, bad, notes

    def _glue(value: int) -> list[int] | None:
        """拆开粘连数字，并记一条告警。"""
        pair = _split_glued(value, upper)
        if pair:
            notes.append(f"「{value}」按 {pair[0]}、{pair[1]} 处理（分隔符可能被 OCR 吞掉）")
        return pair

    low_ok, high_ok = 1 <= low <= upper, 1 <= high <= upper
    if low == high:
        if low_ok:
            numbers.add(low)
        else:
            # 裸的超上限数字（`29`、`_29`）故意不拆：那多半是课程编号残渣，
            # 宁可漏识别也不要凭空造出第 2、9 周（踩坑④）。只有出现在
            # 「范围/多段」这种明确周次结构里，拆分才是安全的。
            pair = _glue(low) if is_range else None
            if pair:
                numbers.update(pair)
            else:
                bad.add(low)
    elif low_ok and high_ok:
        numbers.update(range(min(low, high), max(low, high) + 1))
    elif not low_ok and high_ok:
        # 「46-10」= 逗号被吞 → 4 单独 + 6-10
        pair = _glue(low)
        if pair:
            numbers.add(pair[0])
            numbers.update(range(pair[1], high + 1) if pair[1] <= high else [pair[1]])
        else:
            bad.add(low)
            numbers.add(high)
    elif low_ok:
        # 「3-416」= 16 单独 + 3-4
        pair = _glue(high)
        if pair:
            numbers.add(pair[1])
            numbers.update(range(low, pair[0] + 1) if pair[0] >= low else [pair[0]])
        else:
            bad.add(high)
            numbers.add(low)
    else:
        bad.add(low)
        bad.add(high)
    return numbers, bad, notes


def parse_week_expr(
    expr: str,
    *,
    total: int = 0,
    clamp_max: int = 30,
    parity_hint: str = "",
) -> WeekResult:
    """解析周次表达式。

    参数
    ----
    expr
        原始文本，例如 ``"1-16周"``、``"3-4,6-10周"``、``"第三至八周"``、
        ``"1-16周(单)"``、``"单周"``、``"5"``。
    total
        学期总周数；用于把「全周/单周/双周」还原成具体周次集合，0 表示未知。
    clamp_max
        周次上限保护，超出即丢弃并留告警（防 ``_29`` 这类噪声）。
    parity_hint
        调用方已经判定的单双周（``"odd"``/``"even"``），优先于文本推断。
    """
    raw = "" if expr is None else str(expr)
    result = WeekResult(raw=raw)
    if not raw.strip():
        # 只说了「单周/双周」而没给范围时，调用方会用 parity_hint 告诉我们；
        # 这里必须把它带回去，否则第二次 finalize（合并多来源、界面改格子）
        # 会把「单周」的课悄悄变成全周。
        if parity_hint in ("odd", "even"):
            result.mode = parity_hint
        return result

    text = normalize(raw)

    parity = parity_hint
    if not parity:
        if any(word in raw for word in ODD_WORDS):
            parity = "odd"
        elif any(word in raw for word in EVEN_WORDS):
            parity = "even"
        else:
            # 形如 "1-16(单)" / "1-16(双)" —— 括号里的单字
            if re.search(r"[(（]\s*单\s*[)）]", raw):
                parity = "odd"
            elif re.search(r"[(（]\s*双\s*[)）]", raw):
                parity = "even"
    if "单双" in raw:  # 「单双周都上」= 每周，别被上面的规则误伤
        parity = ""
        result.warnings.append("出现「单双周」，按全周处理。")

    text = _replace_cn_numbers(text)

    numbers: set[int] = set()
    out_of_range: set[int] = set()
    #: 已知学期总周数时以它为准，否则用 clamp_max 兜底
    upper = int(total) if int(total or 0) > 0 else int(clamp_max)
    for token in _SPLIT_RE.split(text):
        # 「1-9(单)」这种写法：括号里只有单双周/备注，先摘掉再当周次片段解析，
        # 否则整段匹配不上，会被误当成「没给具体周次」而按整学期补全。
        token = _PAREN_RE.sub("", token).strip()
        if not token:
            continue
        found, bad, notes = _expand_token(token, upper)
        numbers.update(found)
        out_of_range.update(bad)
        result.warnings.extend(notes)

    if out_of_range:
        result.warnings.append(
            "忽略了不可能的周次："
            + ",".join(str(v) for v in sorted(out_of_range))
        )

    if parity and not numbers:
        # 只说「单周/双周」：按整学期补全（移动端会因长度不足而不推断）
        if total > 0:
            step = 1 if parity == "odd" else 2
            numbers = set(range(step, total + 1, 2))
            result.warnings.append(f"未给出具体周次，按整学期 {total} 周补全{('单' if parity == 'odd' else '双')}周。")
    elif parity:
        before = len(numbers)
        want = 1 if parity == "odd" else 0
        numbers = {n for n in numbers if n % 2 == want}
        if len(numbers) != before:
            result.warnings.append("已按单/双周过滤周次。")

    if not numbers:
        if parity:
            result.mode = parity
        return result

    weeks = sorted(numbers)
    mode, custom_text = infer_mode(weeks, total)
    if parity and mode == "custom" and total > 0:
        # 文本里写了单双周，兜底仍然按 parity 存储，语义最稳。
        # 注意要 total > 0：不知道学期多长时的 custom 结论不作数，
        # resolve_weeks 稍后会带着总周数重新判断，那时再提示才有意义。
        result.warnings.append("单双周信息已并入周次文本。")
    result.weeks = weeks
    result.mode = mode
    result.text = custom_text
    return result


def expand(mode: str, text: str, total: int) -> set[int]:
    """把 ``(mode, text)`` 还原成周次集合（用于去重、校验、预览）。"""
    mode = (mode or "all").lower()
    total = int(total or 0)
    if mode == "all":
        return set(range(1, total + 1)) if total > 0 else set()
    if mode == "odd":
        return set(range(1, total + 1, 2)) if total > 0 else set()
    if mode == "even":
        return set(range(2, total + 1, 2)) if total > 0 else set()
    values: set[int] = set()
    for token in _SPLIT_RE.split(normalize(text)):
        match = _RANGE_RE.match(token)
        if match:
            low, high = sorted((int(match.group(1)), int(match.group(2))))
            values.update(range(low, high + 1))
            continue
        match = _SINGLE_RE.match(token)
        if match:
            values.add(int(match.group(1)))
    return {v for v in values if v >= 1}


def merge_weeks(week_sets) -> set[int]:
    """多段周次的并集（同一门课被拆成多行时用）。"""
    total: set[int] = set()
    for item in week_sets:
        total |= {int(v) for v in item}
    return total
