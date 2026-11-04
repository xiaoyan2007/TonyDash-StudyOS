"""OCR 子进程执行器（由 :mod:`campus_planner.lab_ocr` 调起，跑在 ``lab/.venv`` 里）。

为什么独立成文件而不是 ``python -c``
-------------------------------------
* 子进程参数里带中文路径 / 空格 / 引号时，塞一个长 ``-c`` 字符串在 Windows 上
  很容易踩编码与引号转义的坑；独立文件没有这个问题；
* 可以单独手工调试，不用先起主程序::

    lab\\.venv\\Scripts\\python.exe -u campus_planner\\lab_ocr_runner.py 截图.png

输出约定
--------
* **stderr**：每行 ``PROGRESS {"percent":..,"text":".."}`` 报进度；
* **stdout**：单个 JSON，形如 ``{"ok": true, ...to_payload 结构...}``，
  失败时 ``{"ok": false, "error": "..."}``。

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


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        sys.stderr.write("用法：lab_ocr_runner.py <图片路径> [学期总周数]\n")
        return 2

    target = Path(args[0])
    total = int(args[1]) if len(args) > 1 and str(args[1]).strip() else 0

    def _on_progress(state) -> None:
        """把子解析器的进度原样写回 stderr（父进程会折算回自己的份额）。"""
        sys.stderr.write("PROGRESS " + json.dumps({
            "percent": float(getattr(state, "percent", 0.0)),
            "text": str(getattr(state, "text", "")),
        }, ensure_ascii=False) + "\n")
        sys.stderr.flush()

    try:
        from campus_planner.labkit.ttimport import api

        result = api.parse_file(target, total=total, progress=_on_progress)
        payload = api.to_payload(result, selected_only=False)
        payload["ok"] = True
        payload["source"] = result.source
        sys.stdout.write(json.dumps(payload, ensure_ascii=False))
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
