"""OCR 子进程执行器（由 :mod:`campus_planner.lab_ocr` 调起，跑在 ``lab/.venv`` 里）。

为什么独立成文件而不是 ``python -c``
-------------------------------------
* 子进程参数里带中文路径 / 空格 / 引号时，塞一个长 ``-c`` 字符串在 Windows 上
  很容易踩编码与引号转义的坑；独立文件没有这个问题；
* 可以单独手工调试，不用先起主程序::

    lab\\\\.venv\\\\Scripts\\\\python.exe -u campus_planner\\\\lab_ocr_runner.py 截图.png

**一次进程识别多张图**
----------------------
RapidOCR 的引擎冷启动要 2~3 秒（import onnxruntime + 构造模型）。逐张起子进程时
这部分开销每张都要付一遍；一次进程处理多张只付一次，是「识别图片卡顿」的主要解法。
所以本脚本按「路径列表 → 结果列表」工作，绝不一张一个进程。

输出约定
--------
* **stderr**：每行 ``PROGRESS {"percent":..,"text":".."}`` 报进度（0~100 全程连续）；
* **stdout**：单个 JSON，形如 ``{"ok": true, "results": [payload, ...]}``，
  每个 payload 是 :func:`api.to_payload` 的结构；失败时 ``{"ok": false, "error": "..."}``。

两边互不干扰，父进程按行解析 stderr、最后解析一次 stdout。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

#: 子进程以 `python campus_planner/lab_ocr_runner.py ...` 启动，
#: ``sys.path[0]`` 会被设成脚本所在目录（``campus_planner/``），
#: 而不是工作区根 —— 那样 ``import campus_planner`` 会直接失败。
#: 这里显式把工作区根（``__file__`` 的上两级）补进搜索路径。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

#: **强制 UTF-8 输出**。Windows 上 ``sys.stdout`` 默认是 GBK（代码页 936），
#: 不干预的话中文 JSON 会以 GBK 写出，父进程按 UTF-8 读回来全是 ``\\ufffd``
#: —— 这就是「课表导入结果出现乱码」的根因。父进程 ``Popen`` 用
#: ``encoding="utf-8"`` 读，两边必须一致。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - 个别环境不支持 reconfigure
        pass


def _emit_progress(percent: float, text: str) -> None:
    sys.stderr.write("PROGRESS " + json.dumps({
        "percent": max(0.0, min(100.0, float(percent))),
        "text": str(text),
    }, ensure_ascii=False) + "\n")
    sys.stderr.flush()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        sys.stderr.write(
            "用法：lab_ocr_runner.py <图片1> [图片2 ...] [--total=N]\n")
        return 2

    total = 0
    targets: list[Path] = []
    for item in args:
        if item.startswith("--total="):
            try:
                total = int(item.split("=", 1)[1] or 0)
            except ValueError:
                total = 0
        else:
            targets.append(Path(item))
    if not targets:
        sys.stderr.write("没有可识别的图片路径\n")
        return 2

    count = len(targets)
    results: list[dict] = []
    try:
        from campus_planner.labkit.ttimport import api

        for index, target in enumerate(targets):
            # 每张图占 1/count 的份额，子解析器再把内部进度折算进这一份
            base = index / count
            span = 1.0 / count
            _emit_progress(base * 100, f"识别中 {index + 1}/{count}：{target.name}")

            def _on_progress(state, base=base, span=span) -> None:
                inner = float(getattr(state, "percent", 0.0)) / 100.0
                _emit_progress((base + inner * span) * 100,
                               str(getattr(state, "text", "")))

            result = api.parse_file(target, total=total, progress=_on_progress)
            payload = api.to_payload(result, selected_only=False)
            payload["ok"] = True
            payload["source"] = result.source
            results.append(payload)
            _emit_progress((base + span) * 100, f"完成 {index + 1}/{count}：{target.name}")

        sys.stdout.write(json.dumps({"ok": True, "results": results}, ensure_ascii=False))
        sys.stdout.flush()
        return 0
    except Exception as exc:  # noqa: BLE001 - 子进程任何异常都要变成结构化输出
        sys.stdout.write(json.dumps(
            {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
            ensure_ascii=False))
        sys.stdout.flush()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
