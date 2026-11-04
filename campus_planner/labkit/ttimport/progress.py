"""识别进度回报。

课表识别（OCR / PDF）是**可能持续几十秒**的阻塞式工作，之前界面只能转圈，
用户不知道还要等多久。这里提供一套与解析器解耦的进度回报接口：

* 纯逻辑层（``ttimport`` 各 parser）只认 ``Progress`` 对象，**不依赖任何 UI**，
  这样同一套代码既能在无头脚本里跑（回调打印到控制台），也能在 Qt 里跑。
* UI 层（Qt worker 线程）持有 :class:`Progress`，每次 :meth:`Progress.advance`
  都会触发回调，worker 再把百分比 / 剩余时间通过信号推给主线程。

设计要点：

1. **``total`` 永远是 0~1 的抽象份额**，不是条目数。顶层 ``Progress(total=1.0)``；
   每处理一个文件，用 :meth:`Progress.slice` 切出一份份额，子解析器再把自己的
   内部进度按这份份额折算回去。这样无论嵌套多少层，顶层百分比都连续且不越界。
2. 回调在解析线程里调用，UI 侧必须是**线程安全**的（Qt 用 queued signal）。
3. ``callable(progress)`` 是给旧代码 / 外部调用方留的兼容入口：传一个函数即可，
   无需提前构造对象。

典型用法::

    def on_progress(state):
        print(f"{state.percent:.0f}% {state.text}")

    progress = ttimport.api.parse_many(paths, progress=on_progress)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

__all__ = ["Progress", "as_progress", "ProgressCallback"]

ProgressCallback = Callable[["Progress"], None]


def _fmt_eta(seconds: float) -> str:
    if seconds <= 0 or seconds != seconds:  # 0 / nan
        return "--:--"
    seconds = int(seconds)
    minutes, sec = divmod(seconds, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"


@dataclass
class Progress:
    """一次解析任务的进度句柄。

    可当作 ``slice`` 使用：``state.slice(0.5)`` 得到一个占 ``state`` 一半份额
    的子进度，适合「一个文件占一半、另一个占一半」这种场景。
    """

    total: float = 1.0
    done: float = 0.0
    text: str = ""
    start: float | None = field(default=None, repr=False)
    _parent: "Progress | None" = field(default=None, repr=False)
    _weight: float = field(default=1.0, repr=False)
    _on_advance: ProgressCallback | None = field(default=None, repr=False)

    # ------------------------------------------------------------------ 构造
    def __post_init__(self) -> None:
        if self.start is None:
            import time

            self.start = time.monotonic()

    def slice(self, weight: float, text: str | None = None) -> "Progress":
        """取一份份额，作为子任务的进度句柄。"""
        child = Progress(
            total=1.0,
            text=text or self.text,
            start=self.start,
            _parent=self,
            _weight=max(0.0, float(weight)),
        )
        child.done = 0.0
        return child

    # ------------------------------------------------------------------ 更新
    def _bump(self, amount: float, text: str | None) -> None:
        """本地前进 ``amount``，并把折算后的份额向上冒泡。

        只冒泡**真正推动过本地进度**的增量：一旦本地进度饱和到 ``total``，
        后续空转不再向上冒泡，否则父级会累积超过自己的份额（例如某文件内部
        按行 tick，行数算多了会越过 100%，导致顶层百分比回退）。
        """
        new_done = min(self.total, max(0.0, self.done + amount))
        delta = new_done - self.done
        self.done = new_done
        text_changed = text is not None and text != self.text
        if text_changed:
            self.text = text
        if self._parent is not None:
            if delta or text_changed:
                self._parent._bump(delta * self._weight, self.text)
        elif (delta or text_changed) and self._on_advance is not None:
            try:
                self._on_advance(self)
            except Exception:  # 进度回调出错绝不能影响识别
                pass

    def advance(self, amount: float = 1.0, text: str | None = None) -> "Progress":
        """前进 ``amount``（按当前份额的倍数，通常传 ``1.0 / 分母``）。"""
        self._bump(max(0.0, float(amount)), text)
        return self

    def set(self, done: float, text: str | None = None) -> "Progress":
        """直接把本地进度设成 ``done``（0~1），按增量冒泡。"""
        new = min(self.total, max(0.0, float(done)))
        delta = new - self.done
        self.done = new
        if text is not None and text:
            self.text = text
        if delta:
            if self._parent is not None:
                self._parent._bump(delta * self._weight, self.text)
            elif self._on_advance is not None:
                try:
                    self._on_advance(self)
                except Exception:
                    pass
        return self

    # ------------------------------------------------------------------ 读数
    @property
    def fraction(self) -> float:
        if self.total <= 0:
            return 0.0
        return min(1.0, max(0.0, self.done / self.total))

    @property
    def percent(self) -> float:
        return self.fraction * 100.0

    @property
    def elapsed(self) -> float:
        import time

        return time.monotonic() - (self.start or time.monotonic())

    @property
    def remaining(self) -> float:
        """剩余秒数（用已消耗时间 / 已完成份额推算）。"""
        if self.done <= 0 or self.fraction >= 1.0:
            return 0.0
        elapsed = self.elapsed
        return elapsed / self.fraction - elapsed

    @property
    def eta_text(self) -> str:
        return _fmt_eta(self.remaining)

    def to_dict(self) -> dict:
        return {
            "percent": round(self.percent, 1),
            "text": self.text,
            "remaining": round(self.remaining, 1),
        }

    def __float__(self) -> float:
        return self.fraction


def as_progress(progress, *, total: float = 1.0, text: str = ""):
    """把外部传入的进度参数统一成 :class:`Progress`（或原样返回）。

    支持三种输入：

    * ``None`` → ``None``（调用方自行判断）；
    * ``callable`` → 构造一个 :class:`Progress`，回调接到该函数；
    * ``Progress`` / 字典 → 原样使用（``Progress``）或从 ``current/total`` 还原。
    """
    if progress is None:
        return None
    if isinstance(progress, Progress):
        return progress
    if callable(progress):
        return Progress(total=total, text=text, _on_advance=progress)
    if isinstance(progress, dict):
        return Progress(
            total=float(progress.get("total") or total),
            done=float(progress.get("current") or progress.get("done") or 0.0),
            text=text or str(progress.get("text") or ""),
        )
    return Progress(total=total, text=text)
