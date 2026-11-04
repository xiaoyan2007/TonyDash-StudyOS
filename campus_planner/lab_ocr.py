"""截图 OCR 的子进程服务 —— 把 ``onnxruntime`` 隔离在 ``lab/.venv`` 里。

为什么必须隔离
--------------
OCR 用到的 ``onnxruntime`` / ``rapidocr_onnxruntime`` 装在 ``lab/.venv``
（Python 3.14 + onnxruntime 1.31.1），**主程序的全局 Python 里没有 onnxruntime**，
直接 ``import`` 会 ``ImportError``。而 onnxruntime 必须匹配 CPython 版本，
装进全局环境会污染主程序，风险远大于收益。

所以主进程只做「挑一张图 → 起子进程 → 收进度 → 拿回 :class:`ImportResult`」，
真正识别在 :mod:`campus_planner.lab_ocr_runner` 里跑，那个文件可以单独手工调试。

降级
----
``lab/.venv`` 不在（例如用户只拷贝了打包后的 exe）时，``status()`` 返回
``(False, 修复提示)``，界面会把「识别截图」按钮置灰；
**粘贴文本 / CSV / Excel 导入完全不受影响** —— 那条路不需要任何额外依赖。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .labkit.common import paths

__all__ = [
    "OCRUnavailable", "venv_python", "runner_script", "available",
    "status", "recognize", "TIMEOUT_SECONDS",
]


class OCRUnavailable(RuntimeError):
    """OCR 不可用：缺 venv、子进程启动失败、超时、或输出无法解析。"""


#: 一次截图识别可能要几十秒到几分钟，给足余量（15 分钟）
TIMEOUT_SECONDS = 900

_STATUS: tuple[bool, str] | None = None


def venv_python() -> Path:
    """``lab/.venv`` 的解释器（onnxruntime 只在这里面）。"""
    return paths.WORKSPACE_ROOT / "lab" / ".venv" / "Scripts" / "python.exe"


def runner_script() -> Path:
    """子进程执行的脚本。"""
    return paths.MAIN_PACKAGE / "lab_ocr_runner.py"


def available() -> bool:
    """venv 解释器是否存在。"""
    return venv_python().is_file()


def status(refresh: bool = False) -> tuple[bool, str]:
    """探测 OCR 是否可用，返回 ``(可用, 说明)``；**不抛异常**。

    结果只探测一次并缓存（第一次要 1~3 秒）。
    """
    global _STATUS
    if _STATUS is None or refresh:
        _STATUS = _probe()
    return _STATUS


def _probe() -> tuple[bool, str]:
    py = venv_python()
    if not py.is_file():
        return False, (
            "未找到 OCR 运行环境：lab/.venv 的 Python。"
            "本机全局 Python 没有 onnxruntime，截图识别不可用；"
            "可以改用「粘贴课表文本」或 CSV / Excel 导入，都不需要 OCR。"
        )
    probe = "from rapidocr_onnxruntime import RapidOCR; print('ok')"
    try:
        proc = subprocess.run(
            [str(py), "-u", "-c", probe],
            cwd=str(paths.WORKSPACE_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=300,
        )
    except Exception as exc:  # noqa: BLE001 - 探测失败要变成可读说明，不能崩
        return False, f"调用 lab/.venv 失败：{type(exc).__name__}: {exc}"
    if proc.returncode == 0 and "ok" in (proc.stdout or ""):
        return True, "RapidOCR 可用（lab/.venv + onnxruntime）"
    tail = [line for line in (proc.stderr or proc.stdout or "").splitlines() if line.strip()]
    return False, "OCR 引擎在 lab/.venv 里不可用：" + (tail[-1] if tail else "未知原因")


def recognize(image_path: Any, progress: Any = None):
    """识别一张课表截图，返回 :class:`labkit.ttimport.models.ImportResult`。

    ``progress`` 与 :func:`labkit.ttimport.api.parse_file` 同一约定：
    传回调 ``state -> None``，或直接传 :class:`Progress` 对象都可以。

    失败抛 :class:`OCRUnavailable`，由界面层提示用户。
    """
    from .labkit.ttimport.progress import as_progress

    target = Path(image_path)
    if not target.is_file():
        raise OCRUnavailable(f"图片不存在：{target}")
    ready, reason = status()
    if not ready:
        raise OCRUnavailable(reason)

    progress = as_progress(progress)

    cmd = [str(venv_python()), "-u", str(runner_script()), str(target)]
    try:
        proc = subprocess.Popen(
            cmd, cwd=str(paths.WORKSPACE_ROOT),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
        )
    except OSError as exc:
        raise OCRUnavailable(f"无法启动 OCR 子进程：{type(exc).__name__}: {exc}") from exc

    try:
        stdout, stderr = proc.communicate(timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise OCRUnavailable(f"OCR 超过 {TIMEOUT_SECONDS // 60} 分钟仍未完成，已终止。")

    for line in (stderr or "").splitlines():
        if not line.startswith("PROGRESS "):
            continue
        try:
            data = json.loads(line[len("PROGRESS "):])
        except ValueError:
            continue
        if progress is not None:
            progress.set(float(data.get("percent") or 0.0) / 100.0,
                         text=str(data.get("text") or ""))

    if proc.returncode != 0 or not (stdout or "").strip():
        tail = [x for x in (stderr or "").splitlines() if x.strip()]
        raise OCRUnavailable(
            "OCR 子进程失败：" + " / ".join(tail[-3:] or ["子进程没有输出"]))

    try:
        payload = json.loads(stdout)
    except ValueError as exc:
        raise OCRUnavailable(f"OCR 子进程输出无法解析：{exc}") from exc
    if not payload.get("ok", True):
        raise OCRUnavailable(str(payload.get("error") or "OCR 失败"))

    from .labkit.ttimport import api

    return api.from_payload(payload)
