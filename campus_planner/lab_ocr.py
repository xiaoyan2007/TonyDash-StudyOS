"""截图 OCR 的子进程服务 —— 把 ``onnxruntime`` 隔离在 ``lab/.venv`` 里。

为什么必须隔离
--------------
OCR 用到的 ``onnxruntime`` / ``rapidocr_onnxruntime`` 装在 ``lab/.venv``
（Python 3.14 + onnxruntime 1.31.1），**主程序的全局 Python 里没有 onnxruntime**，
直接 ``import`` 会 ``ImportError``。而 onnxruntime 必须匹配 CPython 版本，
装进全局环境会污染主程序，风险远大于收益。

所以主进程只做「挑图 → 起子进程 → 收进度 → 拿回 :class:`ImportResult`」，
真正识别在 :mod:`campus_planner.lab_ocr_runner` 里跑，那个文件可以单独手工调试。

性能要点：**一次进程识别多张图**
--------------------------------
RapidOCR 引擎冷启动（import onnxruntime + 构造模型）实测 2.7 秒。逐张起子进程时
每张都要付这一遍，3 张图就是 8 秒纯开销。因此本模块提供 :func:`recognize_many`，
把整批图片塞进**同一个**子进程，引擎只初始化一次；:func:`recognize` 只是它的单图包装。

降级
----
``lab/.venv`` 不在（例如用户只拷贝了打包后的 exe）时，``status()`` 返回
``(False, 修复提示)``，界面会把「识别截图」按钮置灰；
**粘贴文本 / CSV / Excel 导入完全不受影响** —— 那条路不需要任何额外依赖。
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Iterable, Sequence

from .labkit.common import paths

__all__ = [
    "OCRUnavailable", "venv_python", "runner_script", "available",
    "status", "recognize", "recognize_many", "TIMEOUT_SECONDS",
]


class OCRUnavailable(RuntimeError):
    """OCR 不可用：缺 venv、子进程启动失败、超时、或输出无法解析。"""


#: 一次截图识别可能要几十秒到几分钟，给足余量（15 分钟）
TIMEOUT_SECONDS = 900

_STATUS: tuple[bool, str] | None = None


def venv_python() -> Path:
    """``lab/.venv`` 的解释器（onnxruntime 只在这里面）。

    打包版里 ``WORKSPACE_ROOT`` 指向 ``_internal``，找不到 venv 时再向上找
    几级目录（开发机上 release/X/_internal → release → 工作区根就能命中
    ``lab/.venv``）；用户机器上都没有 → :func:`status` 返回降级提示。
    """
    default = paths.WORKSPACE_ROOT / "lab" / ".venv" / "Scripts" / "python.exe"
    if default.is_file():
        return default
    base = paths.WORKSPACE_ROOT
    for _ in range(4):
        base = base.parent
        cand = base / "lab" / ".venv" / "Scripts" / "python.exe"
        if cand.is_file():
            return cand
    return default


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
    """识别**一张**课表截图，返回 :class:`labkit.ttimport.models.ImportResult`。

    ``progress`` 与 :func:`labkit.ttimport.api.parse_file` 同一约定：
    传回调 ``state -> None``，或直接传 :class:`Progress` 对象都可以。

    失败抛 :class:`OCRUnavailable`，由界面层提示用户。
    多张图请用 :func:`recognize_many`（共享一次引擎冷启动）。
    """
    results = recognize_many([image_path], progress=progress)
    return results[0]


def recognize_many(image_paths: Sequence[Any], progress: Any = None,
                   total_weeks: int = 0) -> list:
    """**一次子进程**识别多张截图，返回与输入同序的 ``ImportResult`` 列表。

    这是消除「识别图片卡顿」的关键：引擎冷启动只在进程开始时付一次。
    进度是全程连续的 0→100%，界面上看到的是「第 i/N 张 + 张内百分比」。
    """
    from .labkit.ttimport.progress import as_progress

    targets = [Path(item) for item in image_paths]
    if not targets:
        return []
    for target in targets:
        if not target.is_file():
            raise OCRUnavailable(f"图片不存在：{target}")
    ready, reason = status()
    if not ready:
        raise OCRUnavailable(reason)

    progress = as_progress(progress)

    cmd = [str(venv_python()), "-u", str(runner_script())]
    cmd.extend(str(item) for item in targets)
    if total_weeks:
        cmd.append(f"--total={int(total_weeks)}")

    # 子进程必须用 UTF-8 说话：Windows 默认 stdout 是 GBK，中文 JSON 会被
    # 按 GBK 写出去，父进程按 UTF-8 读回来就是一堆 \ufffd（用户看到的"乱码"）。
    # 双保险：环境变量 + 执行器里的 reconfigure（见 lab_ocr_runner.py）。
    child_env = dict(os.environ)
    child_env["PYTHONIOENCODING"] = "utf-8"
    child_env["PYTHONUTF8"] = "1"

    try:
        proc = subprocess.Popen(
            cmd, cwd=str(paths.WORKSPACE_ROOT), env=child_env,
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

    items = payload.get("results")
    if items is None:
        # 兼容旧脚本的「单张返回」形态
        items = [payload]
    return [api.from_payload(item) for item in items]
