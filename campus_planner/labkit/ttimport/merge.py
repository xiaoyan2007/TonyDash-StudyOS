"""多来源课表合并：把「PDF / 多张照片 / Excel / 粘贴文本」解析出的课程
**合并成同一张课表**。

这是本需求的落点：「可以同时识别多张图片，把提取的信息整合为同一张课表」。

合并规则（每一条都对应真实会遇到的情况）：

1. **同一天 + 同一节次 + 同名** → 视为同一门课，合并周次（取并集），
   教师/地点非空的那个胜出（避免某张图恰好没识别到）；
2. **同名但节次不同** → 两个条目（例如同一门课周一第 1-2 节、周三第 3-4 节）；
3. **同名但星期不同** → 同上，各自保留；
4. 教师/地点在某条缺省时，用另一条补上（用户明确要求「缺省留空」，
   但**能补的时候应该补**，所以这里是「有就用有」）。

重复的判定必须用**周次集合**而不是文本，否则 `1-16周` 和 `1-16` 会被当成不同。
"""

from __future__ import annotations

from . import weeks as weeks_mod
from .models import DraftCourse, ImportResult


def _week_set(course: DraftCourse, total: int) -> set[int]:
    if course.week_list:
        return set(course.week_list)
    if course.mode in ("odd", "even", "all"):
        return weeks_mod.expand(course.mode, "", total)
    return set()


def merge_results(results: list[ImportResult], *, source: str = "merged") -> ImportResult:
    """把多个 :class:`ImportResult` 合并成一个。"""
    merged = ImportResult(source=source)
    total = max((r.total_weeks for r in results if r.total_weeks), default=0)

    for result in results:
        merged.warnings.extend(result.warnings)
        merged.periods.extend(result.periods)
        # 每个输入只登记一条来源记录；之前写成按 result.meta 的每个键追加，
        # 会把同一个输入重复登记多次（pdf 3 条、照片各 4 条）。
        merged.meta.setdefault("sources", []).append(
            {"source": result.source, "mode": (result.meta or {}).get("mode")}
        )
        merged.courses.extend(result.courses)

    merged.total_weeks = total or merged.total_weeks
    merged.resolve_weeks()
    _merge_duplicates(merged)
    merged.finalize()
    return merged


def _merge_duplicates(result: ImportResult) -> int:
    """合并「同天 + 同节次 + 同名」的重复课程，返回合并数量。

    与 :meth:`ImportResult.dedupe` 的区别：dedupe 按 ``key`` 做严格相等，
    这里额外做了「教师/地点互补」和「周次合并」。
    """
    by_key: dict[tuple, DraftCourse] = {}
    removed = 0
    for course in result.courses:
        key = (course.name.strip(), int(course.day), int(course.start), int(course.end))
        kept = by_key.get(key)
        if kept is None:
            by_key[key] = course
            continue

        # 周次并集
        union = set(kept.week_list) | set(course.week_list)
        if union:
            kept.week_list = sorted(union)
            kept.mode = "custom"
            kept.weeks_text = weeks_mod.compress_ranges(kept.week_list)
            mode, text = weeks_mod.infer_mode(kept.week_list, result.total_weeks)
            kept.mode = mode
            kept.weeks_text = text
        # 教师/地点：非空者胜出；两边都有且不同则保留更长的那个
        for field in ("teacher", "location"):
            mine = getattr(kept, field, "").strip()
            other = getattr(course, field, "").strip()
            if not mine and other:
                setattr(kept, field, other)
            elif mine and other and mine != other and len(other) > len(mine):
                setattr(kept, field, other)
        removed += 1

    if removed:
        result.courses = list(by_key.values())
        result.warnings.append(f"合并了 {removed} 条重复课程（同天同节次同名）。")
    return removed


__all__ = ["merge_results"]
