"""课表导入对外门面 —— 主程序整合时只需要这一个模块。

设计原则：**这一层不做界面、不碰主程序的数据文件**，只负责
「输入 → :class:`ImportResult`」和「:class:`ImportResult` → 主程序对象」。

主程序未来的整合方式（三行）：:

    from labkit.ttimport import api
    from campus_planner import core
    result = api.parse_file(路径)                    # 或 parse_clipboard / parse_image
    courses = api.build_courses(result, course_cls=core.Course,
                                week_cls=core.WeekSpec, id_factory=core.new_id)
    app.courses.extend(courses)                      # 由主程序决定何时写入 data.json

``build_courses`` 不传 ``course_cls`` 时返回纯 dict，便于在没有主程序的环境里先跑通。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Sequence

from . import ocr as ocr_mod
from . import tabular, text_parser, weeks as weeks_mod
from .models import DraftCourse, ImportResult
from .progress import as_progress

__all__ = [
    "parse_file", "parse_clipboard", "parse_image", "parse_paths", "parse_many",
    "build_courses", "build_periods", "to_payload", "from_payload", "save_payload",
    "summarize", "ocr_status", "pdf_status", "PDF_SUFFIXES",
]

#: 能直接读的文件后缀
TABULAR_SUFFIXES = (".xlsx", ".xlsm", ".csv", ".tsv", ".txt")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff")
PDF_SUFFIXES = (".pdf",)


def _read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gbk", "gb18030", "utf-16"):
        try:
            return path.read_text(encoding=encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def _ocr_image(path: Path) -> tuple[list[dict], float]:
    """对一张图做一次 OCR，返回 ``([{"text","x","y"}], 图片宽度)``。

    这是「列表视图 vs 网格视图」判定与列表解析共用的**唯一一次**整图 OCR：
    旧实现先 :func:`_is_list_view` 跑一遍 OCR，再 ``parse_image_list`` 又跑一遍，
    单张列表视图照片要付两次整图 OCR 的代价。
    """
    recognize = ocr_mod.load_engine()
    image = ocr_mod.load_image(path)
    width = float(image.shape[1])
    placed = getattr(recognize, "placed", None)
    if placed is not None:
        blocks = [{"text": text, "x": x, "y": y} for text, x, y in placed(image)]
    else:
        blocks = [{"text": text, "x": 0.0, "y": float(index * 40)}
                  for index, text in enumerate(recognize(image))]
    return blocks, width


def _looks_list_view(blocks: Sequence[dict]) -> bool:
    """照片是不是「列表视图」（字段带「周数：/上课地点：/教师：」标签）。

    两种版式用不同解析器：列表视图每门课 2~3 行文字，网格视图是格子。
    判据是「有没有出现带冒号的字段标签」——真实截图里两者泾渭分明。
    """
    labels = sum(
        1 for block in blocks
        if any(tag in block.get("text", "")
               for tag in ("周数：", "周数:", "上课地点：", "上课地点:", "教师：", "教师:"))
    )
    return labels >= 2


def _mark(progress, text: str = "") -> None:
    """把（某个文件的）进度置为完成。"""
    if progress is not None:
        progress.set(1.0, text=text or getattr(progress, "text", ""))


def parse_file(path: str | os.PathLike[str], *, total: int = 0,
               progress: Any = None) -> ImportResult:
    """按后缀自动分派：PDF / 表格 / 图片（自动分辨列表视图与网格视图）/ 文本。

    ``progress`` 接收 :class:`labkit.ttimport.progress.Progress`，
    由本函数分派到 PDF / 图片 / 表格解析器并回报进度。
    """
    target = Path(path)
    progress = as_progress(progress)
    suffix = target.suffix.lower()
    if suffix in PDF_SUFFIXES:
        from . import pdf_parser

        try:
            return pdf_parser.parse_pdf(target, progress=progress)
        except Exception as exc:  # noqa: BLE001 - PDF 失败要能降级到 OCR
            result = ImportResult(source="pdf")
            result.warnings.append(f"PDF 解析失败：{type(exc).__name__}: {exc}")
            result.finalize()
            _mark(progress, f"PDF 解析失败 {target.name}")
            return result
    if suffix in (".xlsx", ".xlsm") or suffix in (".csv", ".tsv"):
        result = tabular.parse_file(target)
        _mark(progress, f"解析表格 {target.name}")
        return result
    if suffix in IMAGE_SUFFIXES:
        return parse_image(target, total=total, progress=progress)
    if suffix in (".txt", ".text", ".md"):
        text = _read_text(target)
        result = text_parser.parse_text(text, source="paste")
        result.meta["file"] = str(target)
        _mark(progress, f"解析文本 {target.name}")
        return result
    # 不认识的扩展名：先按表格试，失败再按文本试
    try:
        result = tabular.parse_file(target)
        _mark(progress, f"解析表格 {target.name}")
        return result
    except Exception:  # noqa: BLE001
        result = text_parser.parse_text(_read_text(target), source="paste")
        result.meta["file"] = str(target)
        _mark(progress, f"解析文本 {target.name}")
        return result


def parse_clipboard(text: str, *, total: int = 0) -> ImportResult:
    """解析剪贴板文本。截图 OCR 是猜像素，粘贴文本才是最准的路径。"""
    result = text_parser.parse_text(text, source="paste")
    if total > 0:
        result.total_weeks = total
        result.finalize()
    return result


def parse_image(path: str | os.PathLike[str], *, total: int = 0,
                debug_dir: str | os.PathLike[str] | None = None,
                progress: Any = None) -> ImportResult:
    """解析课表截图：自动分辨「列表视图」与「网格视图」。

    列表视图（字段带「周数：/上课地点：/教师：」标签）用
    :mod:`labkit.ttimport.list_parser`；网格视图用逐格 OCR
    :func:`labkit.ttimport.ocr.parse_image`。

    两种视图共用**一次**整图 OCR：先用 :func:`_ocr_image` 拿到带坐标的文本块，
    列表视图直接把块交给 ``parse_blocks``；网格视图才继续逐格识别。
    （旧实现为了判定版式先跑一遍整图 OCR，又让列表解析再跑一遍。）

    ``progress`` 接收 :class:`labkit.ttimport.progress.Progress`。
    """
    from . import list_parser

    target = Path(path)
    progress = as_progress(progress, text=f"识别图片 {target.name}")
    try:
        blocks, width = _ocr_image(target)
    except Exception:  # noqa: BLE001 - OCR 引擎不可用时交给网格流程抛出可读错误
        return ocr_mod.parse_image(target, total=total, debug_dir=debug_dir, progress=progress)
    if _looks_list_view(blocks):
        return list_parser.parse_blocks(blocks, source="photo", width=width, progress=progress)
    return ocr_mod.parse_image(target, total=total, debug_dir=debug_dir, progress=progress)


def parse_many(paths: Sequence[str | os.PathLike[str]], *, total: int = 0,
               progress: Any = None) -> ImportResult:
    """**把多个来源（PDF + 多张照片 + 表格/文本）合并成同一张课表**。

    这是「同时识别多张图片并整合」的入口：逐个解析，再按
    「同天同节次同名」去重、周次取并集、教师/地点互补。

    ``progress`` 接收 :class:`labkit.ttimport.progress.Progress`（或回调），
    每个输入分到等份份额，子解析器再按实际耗时推进，界面可据此显示
    百分比与剩余时间。
    """
    from .merge import merge_results

    progress = as_progress(progress, text="开始识别")
    results: list[ImportResult] = []
    skipped: list[str] = []
    share = max(1, len(paths))
    for index, item in enumerate(paths):
        if progress is not None:
            progress.set(index / share, text=f"识别中 {index + 1}/{share}：{Path(item).name}")
        slice_progress = progress.slice(1.0 / share) if progress is not None else None
        try:
            results.append(parse_file(item, total=total, progress=slice_progress))
        except Exception as exc:  # noqa: BLE001 - 单个文件失败不能拖垮整批
            skipped.append(f"{Path(item).name}：{type(exc).__name__}: {exc}")
        if progress is not None:
            progress.set((index + 1) / share, text=f"完成 {index + 1}/{share}：{Path(item).name}")
    merged = merge_results(results, source="merged")
    merged.meta["inputs"] = [Path(p).name for p in paths]
    if skipped:
        merged.warnings.extend(skipped)
    if progress is not None:
        progress.set(1.0, text=f"识别完成，共合并 {len(results)} 个来源")
    return merged


def parse_paths(paths: Sequence[str | os.PathLike[str]], *, total: int = 0,
                progress: Any = None) -> ImportResult:
    """把多个输入合并成一个结果（界面里一次拖进多个文件时用）。

    与 :func:`parse_many` 的区别：这里**不去重**，只做简单合并，
    用于「把多张图各自的课程原样拼起来」的场景。

    ``progress`` 接收 :class:`labkit.ttimport.progress.Progress`。
    """
    merged = ImportResult(source="multi")
    progress = as_progress(progress, text="开始识别")
    share = max(1, len(paths))
    for index, item in enumerate(paths):
        if progress is not None:
            progress.set(index / share, text=f"识别中 {index + 1}/{share}：{Path(item).name}")
        slice_progress = progress.slice(1.0 / share) if progress is not None else None
        try:
            result = parse_file(item, total=total, progress=slice_progress)
        except Exception as exc:  # noqa: BLE001 - 单个文件失败不该让整批失败
            merged.warnings.append(f"{Path(item).name}：{exc}")
            continue
        merged.courses.extend(result.courses)
        merged.periods.extend(result.periods)
        merged.warnings.extend(result.warnings)
        merged.meta.setdefault("sources", []).append(result.source)
        if progress is not None:
            progress.set((index + 1) / share, text=f"完成 {index + 1}/{share}：{Path(item).name}")
    merged.finalize()
    merged.dedupe()
    if progress is not None:
        progress.set(1.0, text=f"合并完成，共 {len(merged.courses)} 条课程")
    return merged


def build_courses(result: ImportResult, *, course_cls: Callable[..., Any] | None = None,
                  week_cls: Callable[..., Any] | None = None,
                  id_factory: Callable[[str], str] | None = None,
                  selected_only: bool = True) -> list[Any]:
    """把解析结果变成主程序的课程对象列表。

    - 不传 ``course_cls``：返回 ``dict``（含 ``weeks`` 子字典），零依赖；
    - 传 ``course_cls=core.Course, week_cls=core.WeekSpec, id_factory=core.new_id``：
      返回真正的 ``Course`` 实例，可直接 ``app.courses.extend(...)``。
    """
    courses = result.selected if selected_only else result.courses
    built: list[Any] = []
    for course in courses:
        kwargs = course.to_core_kwargs()
        weeks = kwargs.pop("weeks", {})
        if course_cls is None:
            built.append({**kwargs, "weeks": weeks})
            continue
        if week_cls is not None:
            kwargs["weeks"] = week_cls(**weeks)
        else:
            kwargs["weeks"] = weeks
        if id_factory is not None:
            kwargs["id"] = id_factory("c")
        built.append(course_cls(**kwargs))
    return built


def build_periods(result: ImportResult, *, period_cls: Callable[..., Any] | None = None) -> list[Any]:
    """把解析出的作息时间（第 n 节 08:00-08:45）变成 ``core.Period`` 列表。"""
    out: list[Any] = []
    for item in result.periods:
        start, end = item.get("start", ""), item.get("end", "")
        if not start or not end:
            continue
        out.append(period_cls(start, end) if period_cls is not None else {"start": start, "end": end})
    return out


def to_payload(result: ImportResult, *, selected_only: bool = True) -> dict:
    """序列化成 JSON 友好的结构（独立 schema，便于人工检查与回滚）。

    **必须带全 :class:`DraftCourse` 的原始字段**（尤其 ``mode`` / ``weeks_text`` /
    ``parity`` / ``week_list``）：``to_core_kwargs()`` 只是给主程序 ``Course``
    用的翻译结果，它把周次压成 ``{"mode","text"}``，单/双周与原始文本都会丢。
    子进程（OCR）正是靠这份 JSON 往返还原对象，少一个字段周次就退化成「全周」。
    """
    courses = result.selected if selected_only else result.courses
    return {
        "schema": 2,
        "source": result.source,
        "totalWeeks": result.total_weeks,
        "stats": dict(result.stats),
        "warnings": list(result.warnings),
        "meta": {k: v for k, v in result.meta.items() if k != "cell_text"},
        "courses": [dict(course.to_dict(),
                         weekday=course.weekday_name,
                         weeksLabel=course.weeks_label(result.total_weeks),
                         periodsLabel=course.periods_label,
                         issues=list(course.issues))
                    for course in courses],
        "periods": [dict(item) for item in result.periods],
    }


def from_payload(payload: dict) -> ImportResult:
    """把 :func:`to_payload` 的结构还原成 :class:`ImportResult`。

    主要给 **OCR 子进程**用：onnxruntime 只能在 ``lab/.venv`` 里跑，
    子进程解析完把 :func:`to_payload` 的 JSON 交回主进程，主进程再还原成
    中间模型 —— 这样界面层（预览表格 / 勾选 / 导出）完全不用改。

    兼容旧 schema=1 的载荷（那时用 ``to_core_kwargs`` 序列化，只有
    ``weeks={"mode","text"}``）：把 ``weeks`` 拆成 ``mode`` / ``weeks_text`` 补回来。

    还原出来的课程不重跑 :meth:`ImportResult.finalize`：``to_payload`` 之前
    已经收尾过，重复收尾虽然幂等但会再花一遍时间，用户改完格子时界面
    自己会调 ``finalize``。
    """
    result = ImportResult(
        source=str(payload.get("source") or ""),
        total_weeks=int(payload.get("totalWeeks") or 0),
        warnings=list(payload.get("warnings") or []),
        stats=dict(payload.get("stats") or {}),
        meta=dict(payload.get("meta") or {}),
        periods=list(payload.get("periods") or []),
    )
    fields = DraftCourse.__dataclass_fields__
    for item in payload.get("courses") or []:
        data = {k: v for k, v in item.items() if k in fields}
        if "weeks" in item and isinstance(item["weeks"], dict):
            # 旧 schema=1 的兼容路径
            weeks = item["weeks"]
            data.setdefault("mode", str(weeks.get("mode") or "all"))
            data.setdefault("weeks_text", str(weeks.get("text") or ""))
        result.courses.append(DraftCourse(**data))
    return result


def save_payload(result: ImportResult, path: str | os.PathLike[str],
                 *, selected_only: bool = True) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(to_payload(result, selected_only=selected_only),
                                 ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def summarize(result: ImportResult) -> str:
    """给界面/日志用的一行摘要。"""
    count = len(result.selected)
    total = len(result.courses)
    text = f"识别 {total} 门课"
    if count != total:
        text += f"（勾选 {count} 门）"
    if result.total_weeks:
        text += f"，学期 {result.total_weeks} 周"
    if result.warnings:
        text += f"，{len(result.warnings)} 条提示"
    return text


def ocr_status() -> tuple[bool, str]:
    """OCR 是否可用（界面据此决定「截图导入」按钮是否可点）。"""
    return ocr_mod.engine_available()


def pdf_status() -> tuple[bool, str]:
    """PDF 解析是否可用（缺 pymupdf 时界面应提示）。"""
    from . import pdf_parser

    return pdf_parser.available()
