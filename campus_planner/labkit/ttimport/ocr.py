"""教务系统截图 OCR 课表导入。

流程（照搬 `ghvv-y/timetable-reminder` 精读结论，并修掉它踩过的坑）：

1. **格线检测** —— 先在整图上找横竖格线，得到全局行列边界；
2. **逐格识别** —— 只对「有内容」的格子单独跑 OCR（约 20/84 格），
   既比整图快，也不会像整图那样把相邻格的文字并成一个文本块；
3. **单元格解析** —— 交给 :mod:`labkit.ttimport.cell_parser`，与粘贴文本共用同一套规则。

三条不能动的经验（都来自对参考实现的实测）：

* 格子裁剪**不能**先裁到文字边界再放大，否则 ``第(08:00-08:45)`` 会被切碎；
* 列边界必须全局一致，逐行带检测会把课表切碎、星期错位；
* 空白格用 ``(灰度<215) 的像素比例 < 0.004`` 判定，
  阈值放到 0.015 会把整列时间栏误判成空的。

引擎本身是可插拔的：默认 RapidOCR（onnxruntime），
不可用时给出可执行的修复建议，并让调用方退回到「粘贴文本」这条 100% 准确的路径。
"""

from __future__ import annotations

import ctypes
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from . import cell_parser, fields
from .models import DraftCourse, ImportResult
from .progress import as_progress

try:  # numpy 与 Pillow 是图片路径的硬需求，缺失时给可读提示而不是崩
    import numpy as _np
except Exception:  # noqa: BLE001
    _np = None

try:
    from PIL import Image as _Image
except Exception:  # noqa: BLE001
    _Image = None


class OcrUnavailable(RuntimeError):
    """OCR 引擎不可用：缺依赖、依赖加载失败、或图片路径缺 numpy/Pillow。"""


class GridNotFound(OcrUnavailable):
    """在图里没找到足够规整的格线，无法逐格识别。"""


# --------------------------------------------------------------- 依赖与环境
#: onnxruntime 1.24+ 用 VS2022 新工具链编译，而 CPython 安装目录自带的
#: VC 运行库可能还是 14.29（2019 年版）。本机实测：直接 import 会报
#: 「动态链接库(DLL)初始化例程失败」甚至访问违例，**先把较新的
#: msvcp140/vcruntime140 预载进进程**就正常了。所以这里主动挑最新的那份。
_MSVC_NAMES = ("msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll", "concrt140.dll")
#: 识别置信度下限。引擎默认 0.5，会把浅色小字**整行丢掉**：实测「报告厅」只拿到
#: 0.448（「冯二」0.538 能过），地点列因此整格丢失。这些行后面还要过地点/人名/
#: 周次的正则筛选，宁可先留下来交给规则判，也不要在这里静默扔掉。
DEFAULT_TEXT_SCORE = 0.3
_runtime_note: str = ""
_engine: Callable[[Any], list[str]] | None = None
_engine_name: str = ""


def _file_version(path: Path) -> tuple[int, int, int, int]:
    """读 PE 文件版本号；失败返回 (0,0,0,0)。"""
    try:
        version = ctypes.windll.version
        size = version.GetFileVersionInfoSizeW(str(path), None)
        if not size:
            return (0, 0, 0, 0)
        buf = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(str(path), 0, size, buf):
            return (0, 0, 0, 0)
        ptr = ctypes.c_void_p()
        length = ctypes.c_uint()
        if not version.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(length)):
            return (0, 0, 0, 0)
        raw = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_uint * 4)).contents
        ms, ls = raw[2], raw[3]
        return (ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF)
    except Exception:  # noqa: BLE001
        return (0, 0, 0, 0)


def _runtime_dirs() -> list[Path]:
    """可能放着 VC 运行库的目录（按用处从高到低）。"""
    dirs: list[Path] = []
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    dirs.append(Path(system_root) / "System32")
    try:
        dirs.append(Path(sys.base_prefix))
        dirs.append(Path(sys.base_prefix) / "DLLs")
    except Exception:  # noqa: BLE001
        pass
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if entry:
            dirs.append(Path(entry))
    unique: list[Path] = []
    for item in dirs:
        if item.is_dir() and item not in unique:
            unique.append(item)
    return unique


def preload_msvc_runtime() -> str:
    """把版本最新的 msvcp140/vcruntime140 预载进进程，返回说明文字。

    必须在 ``import onnxruntime`` **之前**调用，否则 onnxruntime 会先绑定
    到 CPython 自带的那份旧运行库上，之后无法换回。
    """
    global _runtime_note
    if _runtime_note:
        return _runtime_note
    candidates: list[tuple[tuple[int, int, int, int], Path]] = []
    for directory in _runtime_dirs():
        msvcp = directory / "msvcp140.dll"
        if msvcp.exists():
            candidates.append((_file_version(msvcp), directory))
    if not candidates:
        _runtime_note = "系统里没找到 msvcp140.dll，交给 Windows 自己按默认搜索路径解析。"
        return _runtime_note
    candidates.sort(key=lambda item: (item[0], str(item[1]) == str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32")), reverse=True)
    version, best = candidates[0]
    loaded: list[str] = []
    for name in _MSVC_NAMES:
        dll = best / name
        if not dll.exists():
            continue
        try:
            ctypes.WinDLL(str(dll))
            loaded.append(name)
        except OSError:
            continue
    try:  # Python 3.8+ 需要显式声明 DLL 目录，扩展模块才找得到同目录依赖
        os.add_dll_directory(str(best))
    except (AttributeError, OSError, FileNotFoundError):
        pass
    version_text = ".".join(str(x) for x in version)
    _runtime_note = f"预载 VC 运行库 {version_text}（{best}）：{', '.join(loaded) or '无可加载项'}"
    return _runtime_note


def engine_available() -> tuple[bool, str]:
    """探测 OCR 引擎是否可用，返回 ``(可用, 说明)``；不抛异常。"""
    if _np is None or _Image is None:
        return False, "缺少 numpy / Pillow，无法处理图片。"
    try:
        preload_msvc_runtime()
        import onnxruntime  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        return False, (
            "onnxruntime 加载失败："
            f"{type(exc).__name__}: {exc}\n"
            "修复建议：pip install --no-deps <onnxruntime 的 cp3xx 轮子>（本机已验证 1.31.1 可用），"
            "或改用「粘贴课表文本」导入（准确率 100%，不需要任何依赖）。"
        )
    try:
        from rapidocr_onnxruntime import RapidOCR  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        return False, f"rapidocr_onnxruntime 不可用：{type(exc).__name__}: {exc}"
    return True, "RapidOCR(onnxruntime) 可用"


def load_engine(**options: Any) -> Callable[[Any], list[str]]:
    """加载并缓存 OCR 引擎。返回 ``图片区域 -> 文本行列表`` 的可调用对象。

    返回的可调用对象上还挂着 ``placed``，即 ``区域 -> [(文本, 中心x, 中心y)]``
    （坐标以区域左上角为原点）。逐格识别时用它做「文字中心必须落在格内」的
    过滤：格子下沿常把最后一行的字压掉一半，把裁剪范围外扩几像素再按中心过
    滤，既能把压线的字认全，又不会把邻格的文字混进来。
    """
    global _engine, _engine_name
    if _engine is not None:
        return _engine
    if _np is None or _Image is None:
        raise OcrUnavailable("缺少 numpy / Pillow，无法处理图片。")
    preload_msvc_runtime()
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception as exc:  # noqa: BLE001
        raise OcrUnavailable(f"OCR 引擎不可用：{engine_available()[1]}") from exc
    options.setdefault("text_score", DEFAULT_TEXT_SCORE)
    recognizer = RapidOCR(**options)

    def _placed(region: Any) -> list[tuple[str, float, float]]:
        result, _elapse = recognizer(region)
        if not result:
            return []
        placed: list[tuple[str, float, float]] = []
        for item in result:
            if len(item) < 2 or not item[1]:
                continue
            text = str(item[1]).strip()
            if not text:
                continue
            box = item[0]
            try:
                xs = [float(point[0]) for point in box]
                ys = [float(point[1]) for point in box]
                center = (sum(xs) / len(xs), sum(ys) / len(ys))
            except Exception:  # noqa: BLE001 - 拿不到坐标就当作在区域内
                center = (0.0, 0.0)
            placed.append((text, center[0], center[1]))
        placed.sort(key=lambda entry: (entry[2], entry[1]))
        return placed

    def _recognize(region: Any) -> list[str]:
        return [text for text, _x, _y in _placed(region)]

    _recognize.placed = _placed  # type: ignore[attr-defined]
    _engine = _recognize
    _engine_name = "rapidocr-onnxruntime"
    return _engine


def engine_name() -> str:
    return _engine_name


def runtime_note() -> str:
    return _runtime_note


# --------------------------------------------------------------- 图片与格线
#: 参考实现实测：真空白格 ≈0.0001、时间栏 ≈0.0134、课程格 0.02~0.06。
#: 阈值设成 0.015 会把时间栏整列判空，所以取 0.004。
BLANK_INK_RATIO = 0.004
INK_GRAY = 215
#: 判定「这条像素属于格线」：颜色接近灰色（彩条/彩底不算）且整体偏暗
LINE_CHROMA = 26
LINE_GRAY = 232


def load_image(path: str | os.PathLike[str]) -> Any:
    """读成 RGB numpy 数组。"""
    if _np is None or _Image is None:
        raise OcrUnavailable("缺少 numpy / Pillow，无法读取图片。")
    candidate = Path(path)
    if not candidate.exists():
        raise OcrUnavailable(f"图片不存在：{candidate}")
    with _Image.open(candidate) as image:
        return _np.asarray(image.convert("RGB"))


def _runs(ratio: Any, threshold: float) -> list[tuple[int, int]]:
    """找出连续 ``> threshold`` 的区间（含首尾）。"""
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(ratio):
        on = bool(value > threshold)
        if on and start is None:
            start = index
        elif not on and start is not None:
            spans.append((start, index - 1))
            start = None
    if start is not None:
        spans.append((start, len(ratio) - 1))
    return spans


def _dedupe(positions: Sequence[int], min_gap: int) -> list[int]:
    """把挨得太近的重复线并成一条（线宽 2px 时常被投影成两段）。"""
    if not positions:
        return []
    groups: list[list[int]] = [[positions[0]]]
    for position in positions[1:]:
        if position - groups[-1][-1] < min_gap:
            groups[-1].append(position)
        else:
            groups.append([position])
    return [int(round(sum(group) / len(group))) for group in groups]


def _longest_chain(positions: Sequence[int], base: float, tol: float) -> list[int]:
    """最长的一条「相邻间距≈base」的连线。"""
    best: list[int] = []
    current: list[int] = [positions[0]]
    for previous, position in zip(positions, positions[1:]):
        if abs((position - previous) - base) <= base * tol:
            current.append(position)
        else:
            if len(current) > len(best):
                best = current
            current = [position]
    if len(current) > len(best):
        best = current
    return best


def _axis_lines(ratio: Any, threshold: float, *, min_gap: int = 40, tol: float = 0.35) -> list[int]:
    """一条轴上的格线坐标：取连续段中心 → 合并重复 → 留最长规则链 → 补回两端外框线。

    关键点：**不能**用「与上一条已保留线比较」的贪心剔除——表头那一段间距
    （例如 78px）与正文行高（142px）不同，贪心会让表头之后的线全部被判为
    不规整而丢掉，只剩 1 条线。这里改成先选出最长的规则链，再把链两端外侧
    最近的那条线补回来（即课表的上下/左右外框）。
    """
    spans = _runs(ratio, threshold)
    centers = _dedupe([(start + end) // 2 for start, end in spans], min_gap)
    if len(centers) < 3:
        return centers
    gaps = [b - a for a, b in zip(centers, centers[1:])]
    big = [gap for gap in gaps if gap >= min_gap] or gaps
    base = float(_np.median(big))
    if base <= 0:
        return centers
    chain = _longest_chain(centers, base, tol)
    if len(chain) < 3:
        return chain if len(chain) > 1 else centers
    head, tail = chain[0], chain[-1]
    before = [c for c in centers if c < head]
    after = [c for c in centers if c > tail]
    if before and head - before[-1] >= min_gap:
        chain = [before[-1]] + chain
    if after and after[0] - tail >= min_gap:
        chain = chain + [after[0]]
    return chain


def find_grid_lines(image: Any, h_tol: float = 0.60, v_tol: float = 0.55) -> tuple[list[int], list[int]]:
    """返回 ``(横线 y 坐标, 竖线 x 坐标)``，均为升序。"""
    if _np is None:
        raise OcrUnavailable("缺少 numpy。")
    array = _np.asarray(image)
    if array.ndim == 2:
        array = _np.stack([array] * 3, axis=-1)
    gray = array[..., :3].mean(axis=2)
    chroma = array[..., :3].max(axis=2) - array[..., :3].min(axis=2)
    lineish = (chroma < LINE_CHROMA) & (gray < LINE_GRAY)
    if not lineish.any():
        return [], []
    ys = _axis_lines(lineish.mean(axis=1), h_tol)
    xs = _axis_lines(lineish.mean(axis=0), v_tol)
    return ys, xs


def detect_grid(image: Any) -> tuple[list[int], list[int], float]:
    """找格线；第一遍不达标就用参考实现建议的宽松阈值再试一次。"""
    ys, xs = find_grid_lines(image)
    if len(ys) >= 3 and len(xs) >= 3:
        return ys, xs, 0.0
    ys2, xs2 = find_grid_lines(image, h_tol=0.45, v_tol=0.40)
    if len(ys2) * len(xs2) > len(ys) * len(xs):
        return ys2, xs2, 1.0
    return ys, xs, 0.0


@dataclass
class GridCell:
    """一格：行列号、像素框、以及是否空白。"""

    row: int
    col: int
    box: tuple[int, int, int, int]   # x0, y0, x1, y1
    blank: bool = False
    text_lines: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.text_lines)


def split_cells(image: Any, ys: Sequence[int], xs: Sequence[int],
                *, inset_start: int = 2, inset_end: int = 1) -> list[GridCell]:
    """按全局行列边界切格，**内缩**几像素避开格线本身。"""
    if _np is None:
        raise OcrUnavailable("缺少 numpy。")
    array = _np.asarray(image)
    if array.ndim == 2:
        array = _np.stack([array] * 3, axis=-1)
    cells: list[GridCell] = []
    for row in range(len(ys) - 1):
        y0 = min(int(ys[row]) + inset_start, array.shape[0])
        y1 = max(int(ys[row + 1]) - inset_end, y0 + 1)
        for col in range(len(xs) - 1):
            x0 = min(int(xs[col]) + inset_start, array.shape[1])
            x1 = max(int(xs[col + 1]) - inset_end, x0 + 1)
            sub = array[y0:y1, x0:x1]
            blank = sub.size == 0 or bool((sub[..., :3].mean(axis=2) < INK_GRAY).mean() < BLANK_INK_RATIO)
            cells.append(GridCell(row=row, col=col, box=(x0, y0, x1, y1), blank=blank))
    return cells


def crop(image: Any, box: tuple[int, int, int, int]) -> Any:
    x0, y0, x1, y1 = box
    return _np.asarray(image)[y0:y1, x0:x1]


def _read_cell(image: Any, box: tuple[int, int, int, int],
               recognize: Callable[[Any], list[str]], margin: int = 4) -> list[str]:
    """识别一个格子里的文字。

    裁剪框会**向外多留 margin 像素**，再只保留「文字中心落在原格内」的行。
    真实教务截图里最后一行（周次）常压着横向格线，按格内裁剪会把字的下半截
    切掉（实测「1-16周」被读成「16周」）；外扩后能认全，而邻格文字的中心在
    格线之外，会被中心过滤挡住，不会串格。
    """
    placed = getattr(recognize, "placed", None)
    if placed is None:
        return list(recognize(crop(image, box)))
    height, width = int(image.shape[0]), int(image.shape[1])
    x0, y0, x1, y1 = box
    grown = (max(0, x0 - margin), max(0, y0 - margin),
             min(width, x1 + margin), min(height, y1 + margin))
    lines: list[str] = []
    for text, center_x, center_y in placed(crop(image, grown)):
        if x0 <= grown[0] + center_x <= x1 and y0 <= grown[1] + center_y <= y1:
            lines.append(text)
    return lines


# --------------------------------------------------------------- 行列 → 星期/节次
def map_axes(header_lines: Sequence[Sequence[str]],
             period_lines: Sequence[Sequence[str]]) -> tuple[dict[int, int], dict[int, tuple[int, int]]]:
    """把「表头行 / 节次列」的识别结果映射成列→星期、行→节次区间。

    ``header_lines[col]`` 是第 col 个表头格的文本行，``period_lines[row]`` 同理。
    识别不出来时退化成「第 1 列是周一、每行两节」，保证总能出结果。
    """
    day_of_col: dict[int, int] = {}
    for index, lines in enumerate(header_lines, start=1):
        for line in lines:
            day = fields.extract_weekday(line)
            if day:
                day_of_col[index] = int(day)
                break
    span_of_row: dict[int, tuple[int, int]] = {}
    for index, lines in enumerate(period_lines, start=1):
        for line in lines:
            periods = fields.extract_periods(line)
            if periods:
                span_of_row[index] = (int(periods[0]), int(periods[1]))
                break
    return day_of_col, span_of_row


def _fallback_day(col: int) -> int:
    return max(1, min(7, col))


def _fallback_span(row: int) -> tuple[int, int]:
    return (row * 2 - 1, row * 2)


def collect_periods(period_lines: Sequence[Sequence[str]],
                    span_of_row: dict[int, tuple[int, int]]) -> list[dict]:
    """从左侧时间栏抽出每个节次的上下课时间，去重后按节次排序。

    少了时间不算错（课表照样能导入，主程序用默认作息），所以宁可少一条也不猜。
    """
    found: dict[int, dict] = {}
    for index, lines in enumerate(period_lines, start=1):
        text = " ".join(lines)
        if not text.strip():
            continue
        first = span_of_row.get(index, _fallback_span(index))[0]
        for item in cell_parser.time_slot_dicts(text, first):
            found.setdefault(item["period"], item)
    return [found[key] for key in sorted(found)]


# --------------------------------------------------------------- 主流程
def parse_image(path: str | os.PathLike[str], *, engine: Callable[[Any], list[str]] | None = None,
                debug_dir: str | os.PathLike[str] | None = None,
                total: int = 0, progress: Any = None) -> ImportResult:
    """把一张课表截图解析成 :class:`ImportResult`。

    失败时抛 :class:`OcrUnavailable` / :class:`GridNotFound`，
    调用方应捕获并提示用户改走粘贴文本。

    ``progress`` 接收 :class:`labkit.ttimport.progress.Progress`（或回调）；
    网格识别把「检测格线 + 表头 + 节次 + 逐格」分成若干等份回报，
    让调用方能显示百分比与剩余时间。
    """
    if _np is None or _Image is None:
        raise OcrUnavailable("缺少 numpy / Pillow，无法处理图片。")
    recognize = engine or load_engine()
    image = load_image(path)
    result = ImportResult(source="ocr")
    result.meta["image_size"] = [int(image.shape[1]), int(image.shape[0])]
    progress = as_progress(progress, text=f"识别图片 {Path(path).name}")

    ys, xs, relaxed = detect_grid(image)
    result.meta["grid"] = {"ys": ys, "xs": xs, "relaxed": bool(relaxed)}
    if len(ys) < 3 or len(xs) < 3:
        raise GridNotFound(
            f"没能在这张图上找到足够规整的格线（横线 {len(ys)} 条、竖线 {len(xs)} 条）。"
            "请换一张更清晰的整屏截图，或直接复制课表文本用「粘贴导入」。"
        )

    cells = split_cells(image, ys, xs)
    result.meta["cells"] = len(cells)
    by_position = {(cell.row, cell.col): cell for cell in cells}
    rows = len(ys) - 1
    cols = len(xs) - 1

    # 进度按「检测格线 + 表头 + 节次 + 非空格」分摊，单元格通常最多，
    # 这样百分比和剩余时间能跟着实际耗时走。
    steps = max(1, 1 + (cols - 1) + (rows - 1)
                + sum(1 for cell in cells if not cell.blank and cell.row > 0 and cell.col > 0))

    def tick(text: str = "") -> None:
        if progress is not None:
            progress.advance(1.0 / steps, text=text or progress.text)

    if progress is not None:
        progress.set(0.0, text=f"识别图片 {Path(path).name}")
        progress.advance(1.0 / steps, text="检测格线")

    header_lines: list[list[str]] = []
    period_lines: list[list[str]] = []
    for col in range(1, cols):
        cell = by_position.get((0, col))
        if cell and not cell.blank:
            cell.text_lines = _read_cell(image, cell.box, recognize)
            tick(f"识别表头第 {col} 列")
        header_lines.append(list(cell.text_lines) if cell else [])
    for row in range(1, rows):
        cell = by_position.get((row, 0))
        if cell and not cell.blank:
            cell.text_lines = _read_cell(image, cell.box, recognize)
            tick(f"识别节次第 {row} 行")
        period_lines.append(list(cell.text_lines) if cell else [])

    day_of_col, span_of_row = map_axes(header_lines, period_lines)
    result.periods.extend(collect_periods(period_lines, span_of_row))
    result.meta["mapped_days"] = len(day_of_col)
    result.meta["mapped_periods"] = len(span_of_row)
    result.meta["period_times"] = len(result.periods)
    if not day_of_col:
        result.warnings.append("表头没认出星期，已按「第 1 列 = 周一」处理。")
    if not span_of_row:
        result.warnings.append("左侧没认出节次，已按「每行两节」处理。")

    debug_rows: list[list[str]] = [["row", "col", "day", "start", "end", "blank", "text"]]
    cell_text: dict[str, str] = {}
    for row in range(1, rows):
        for col in range(1, cols):
            cell = by_position.get((row, col))
            if cell is None:
                continue
            if not cell.blank and not cell.text_lines:
                cell.text_lines = _read_cell(image, cell.box, recognize)
                tick(f"识别第 {row}-{col} 格")
            cell_text[f"{row},{col}"] = cell.text
            day = day_of_col.get(col, _fallback_day(col))
            start, end = span_of_row.get(row, _fallback_span(row))
            debug_rows.append([str(row), str(col), str(day), str(start), str(end),
                               "1" if cell.blank else "0", cell.text.replace("\n", " / ")])
            if cell.blank or not cell.text_lines:
                continue
            course = cell_parser.parse_cell(
                cell.text_lines, day=day, start=start, end=end,
                source="ocr", raw=cell.text,
            )
            if course is not None:
                result.courses.append(course)

    result.courses = cell_parser.merge_adjacent(result.courses)
    result.finalize()
    if progress is not None:
        progress.set(1.0, text="识别完成")
    result.meta["engine"] = _engine_name or getattr(recognize, "name", "custom")
    result.meta["cell_text"] = cell_text
    if debug_dir:
        _write_debug(Path(debug_dir), image, cells, debug_rows, result)
    return result


def _write_debug(directory: Path, image: Any, cells: Iterable[GridCell],
                 rows: list[list[str]], result: ImportResult) -> None:
    """把逐格识别结果落盘，方便对着截图定位问题格。"""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "cells.csv").write_text(
            "\n".join(",".join('"' + item.replace('"', '""') + '"' for item in row) for row in rows),
            encoding="utf-8-sig",
        )
        for cell in cells:
            if cell.blank or not cell.text_lines:
                continue
            x0, y0, x1, y1 = cell.box
            #: 存的是外扩 margin 后的区域，即引擎真正看到的那块图，方便对着看串格/压线
            height, width = int(image.shape[0]), int(image.shape[1])
            grown = (max(0, x0 - 4), max(0, y0 - 4), min(width, x1 + 4), min(height, y1 + 4))
            _Image.fromarray(crop(image, grown)).save(directory / f"r{cell.row}c{cell.col}.png")
    except Exception:  # noqa: BLE001 - 调试输出失败不该影响导入
        pass


def parse_clipboard(text: str, *, total: int = 0) -> ImportResult:
    """截图之外的退路：直接解析粘贴来的课表文本（准确率 100%）。"""
    from . import text_parser

    result = text_parser.parse_text(text, source="paste")
    if total:
        result.total_weeks = total
    result.finalize()
    return result


__all__ = [
    "BLANK_INK_RATIO", "GridCell", "GridNotFound", "OcrUnavailable",
    "crop", "detect_grid", "engine_available", "engine_name", "find_grid_lines",
    "load_engine", "load_image", "map_axes", "parse_clipboard", "parse_image",
    "preload_msvc_runtime", "runtime_note", "split_cells",
]
